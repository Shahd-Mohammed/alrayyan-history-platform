import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from alrayyan.extensions import db
from alrayyan.forms import ClassroomForm, ConceptMapForm, ConceptMapUploadForm, CurriculumUploadForm, HistoricalCharacterForm, InvitationForm, LearningResourceForm, PlatformSettingsForm
from alrayyan.models import Classroom, ConceptMap, ConceptMapEdge, ConceptMapNode, ConceptMastery, ContentChunk, Curriculum, HistoricalCharacter, HonorBoardEntry, LearningResource, Lesson, PlatformSettings, SourceDocument, StudentInvitation, TutorMessage, Unit, User, Worksheet, WorksheetAttempt, ChallengeSession
from alrayyan.services.document_reader import calculate_checksum, extract_docx, extract_pdf
from alrayyan.services.text_processing import chunk_text, create_text_hash
from alrayyan.services.curriculum_processing import process_source_document
from alrayyan.services.learning_content_ai import (
    generate_character_drafts,
    generate_concept_map_draft,
)
from alrayyan.services.embeddings import generate_embeddings, get_embedding_settings

platform_admin_bp = Blueprint("platform_admin", __name__, url_prefix="/teacher-dashboard/platform")


@platform_admin_bp.before_request
@login_required
def teacher_only():
    if current_user.role not in {"teacher", "admin"}:
        abort(403)


def teacher_curricula():
    query = Curriculum.query
    if current_user.role != "admin":
        query = query.filter((Curriculum.created_by_id == current_user.id) | (Curriculum.created_by_id.is_(None)))
    return query


def teacher_lessons():
    return Lesson.query.join(Unit).join(Curriculum).filter(
        ((Curriculum.created_by_id == current_user.id) | (Curriculum.created_by_id.is_(None))),
        Curriculum.is_active.is_(True),
        Curriculum.processing_status == "ready",
    ).order_by(Curriculum.subject, Unit.order_index, Lesson.order_index).all()


def lesson_choices():
    return [(lesson.id, f"{lesson.unit.curriculum.subject} — {lesson.title}") for lesson in teacher_lessons()]


def curriculum_ready_for_activation(curriculum):
    if curriculum.processing_status != "ready" or not curriculum.sources:
        return False
    chunks = ContentChunk.query.join(SourceDocument).filter(
        SourceDocument.curriculum_id == curriculum.id,
    ).all()
    return bool(chunks) and all(
        chunk.embedding and chunk.embedding_model and chunk.embedding_dimensions
        for chunk in chunks
    )


def normalize_active_curricula():
    """Keep exactly one active curriculum for each subject and grade."""
    curricula = Curriculum.query.order_by(
        Curriculum.subject,
        Curriculum.grade,
        Curriculum.activated_at.desc().nullslast(),
        Curriculum.created_at.desc(),
        Curriculum.id.desc(),
    ).all()

    active_by_group = {}
    changed = False

    for curriculum in curricula:
        if not curriculum.is_active:
            continue

        group = (curriculum.subject, curriculum.grade)
        if group in active_by_group:
            curriculum.is_active = False
            for source in curriculum.sources:
                source.is_active = False
            changed = True
        else:
            active_by_group[group] = curriculum

    if changed:
        db.session.commit()

    return active_by_group


def activate_curriculum(curriculum):
    if not curriculum_ready_for_activation(curriculum):
        raise ValueError("المنهج لم يكتمل تجهيزه وفهرسته: يجب أن تكون كل المقاطع مستخرجة ومفهرسة بالـembeddings قبل التفعيل.")

    # The active curriculum is a platform-wide choice for the same
    # subject and grade, so never limit this update to the current teacher.
    Curriculum.query.filter(
        Curriculum.id != curriculum.id,
        Curriculum.subject == curriculum.subject,
        Curriculum.grade == curriculum.grade,
    ).update({Curriculum.is_active: False}, synchronize_session=False)

    SourceDocument.query.filter(
        SourceDocument.curriculum_id != curriculum.id,
        SourceDocument.curriculum_id.in_(
            db.session.query(Curriculum.id).filter(
                Curriculum.subject == curriculum.subject,
                Curriculum.grade == curriculum.grade,
            )
        ),
    ).update({SourceDocument.is_active: False}, synchronize_session=False)

    curriculum.is_active = True
    curriculum.processing_status = "ready"
    curriculum.activated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    for source in curriculum.sources:
        source.is_active = True


def owned_lesson_or_404(lesson_id):
    lesson = db.session.get(Lesson, lesson_id)
    if lesson is None or lesson.id not in {item.id for item in teacher_lessons()}:
        abort(404)
    return lesson


def save_upload(upload, folder_name, allowed):
    original = (upload.filename or "").strip()
    extension = Path(original).suffix.lower()
    if extension.lstrip(".") not in allowed:
        raise ValueError("صيغة الملف غير مسموحة")
    folder = Path(current_app.config["UPLOAD_FOLDER"]) / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{extension}"
    path = folder / stored_name
    upload.save(path)
    return original, path, str(Path(folder_name) / stored_name)


@platform_admin_bp.route("/curricula", methods=["GET", "POST"])
def curricula():
    form = CurriculumUploadForm()
    if form.validate_on_submit():
        stored_path = None
        try:
            stored_path = None
            original, stored_path, relative = save_upload(form.document.data, "curricula", {"pdf", "docx"})
            curriculum_query = teacher_curricula().filter_by(
                subject=form.subject.data.strip(),
                grade=form.grade.data.strip(),
                semester=form.semester.data,
                academic_year=form.academic_year.data.strip(),
            ).order_by(Curriculum.created_at.desc())
            curriculum = curriculum_query.first()
            if curriculum is None or curriculum.is_active:
                versions = [str(item.version) for item in curriculum_query.all()]
                version_numbers = []
                for version in versions:
                    try:
                        version_numbers.append(float(version))
                    except (TypeError, ValueError):
                        continue
                next_version = f"{(max(version_numbers) + 1.0) if version_numbers else 1.0:.1f}"
                curriculum = Curriculum(
                    created_by_id=current_user.id,
                    name=form.curriculum_name.data.strip(),
                    subject=form.subject.data.strip(),
                    grade=form.grade.data.strip(),
                    semester=form.semester.data,
                    academic_year=form.academic_year.data.strip(),
                    version=next_version,
                    is_active=False,
                    processing_status="processing",
                )
                db.session.add(curriculum)
                db.session.flush()
            else:
                curriculum.processing_status = "processing"
                curriculum.processing_error = None
                curriculum.is_active = False
                for source in curriculum.sources:
                    source.is_active = False

            checksum = calculate_checksum(stored_path)
            if SourceDocument.query.filter_by(curriculum_id=curriculum.id, checksum=checksum).first():
                raise ValueError("هذا الملف موجود مسبقًا داخل المنهج نفسه")

            unit = Unit.query.filter_by(
                curriculum_id=curriculum.id,
                title=form.unit_title.data.strip(),
            ).first()
            if unit is None:
                unit = Unit(
                    curriculum_id=curriculum.id,
                    title=form.unit_title.data.strip(),
                    order_index=len(curriculum.units) + 1,
                )
                db.session.add(unit)
                db.session.flush()

            lesson = Lesson.query.filter_by(
                unit_id=unit.id,
                title=form.lesson_title.data.strip(),
            ).first()
            if lesson is None:
                lesson = Lesson(
                    unit_id=unit.id,
                    title=form.lesson_title.data.strip(),
                    slug=f"lesson-{uuid4().hex[:16]}",
                    order_index=len(unit.lessons) + 1,
                    is_published=True,
                )
                db.session.add(lesson)
                db.session.flush()

            extracted = extract_pdf(stored_path) if stored_path.suffix.lower() == ".pdf" else extract_docx(stored_path)
            source_priority = {"official_book": 1, "supporting_book": 2, "review_notes": 3}[form.source_type.data]
            source = SourceDocument(
                curriculum_id=curriculum.id,
                lesson_id=lesson.id,
                title=form.source_title.data.strip(),
                source_type=form.source_type.data,
                original_filename=original,
                stored_path=relative,
                page_count=extracted.get("page_count"),
                checksum=checksum,
                academic_year=curriculum.academic_year,
                priority=source_priority,
                is_primary=form.source_type.data == "official_book",
                is_active=True,
            )
            db.session.add(source)
            db.session.flush()

            extracted_count = process_source_document(source)
            activate_curriculum(curriculum)
            db.session.commit()
            flash(
                f"تم تحليل وفهرسة {extracted_count} مقطعًا وتفعيل منهج الفصل {curriculum.semester} في جميع أقسام المنصة.",
                "success",
            )
            return redirect(url_for("platform_admin.curricula"))
        except Exception as error:
            db.session.rollback()
            if stored_path and stored_path.exists():
                stored_path.unlink()
            current_app.logger.exception("Curriculum upload failed")
            flash(f"تعذر تجهيز المصدر: {error}", "error")

    normalize_active_curricula()

    return render_template(
        "platform/curricula.html",
        form=form,
        curricula=teacher_curricula().order_by(Curriculum.created_at.desc()).all(),
    )


@platform_admin_bp.post("/curricula/<int:curriculum_id>/reindex")
def reindex_curriculum(curriculum_id):
    curriculum = teacher_curricula().filter_by(id=curriculum_id).first_or_404()
    if not curriculum.sources:
        flash("لا يوجد ملف مصدر لإعادة تجهيزه داخل هذا المنهج.", "error")
        return redirect(url_for("platform_admin.curricula"))

    try:
        curriculum.processing_status = "processing"
        curriculum.processing_error = None
        total_chunks = 0
        for source in curriculum.sources:
            total_chunks += process_source_document(source)

        curriculum.processing_status = "ready"
        db.session.commit()
        flash(
            f"تمت إعادة تجهيز وفهرسة {total_chunks} مقطعًا. يمكنك الآن تفعيل المنهج.",
            "success",
        )
    except Exception as error:
        db.session.rollback()
        current_app.logger.exception("Curriculum reindex failed")
        flash(f"تعذر إعادة تجهيز المنهج: {error}", "error")

    return redirect(url_for("platform_admin.curricula"))


@platform_admin_bp.post("/curricula/<int:curriculum_id>/delete")
def delete_curriculum(curriculum_id):
    curriculum = teacher_curricula().filter_by(id=curriculum_id).first_or_404()
    relative_paths = [source.stored_path for source in curriculum.sources if source.stored_path]
    was_active = curriculum.is_active

    try:
        db.session.delete(curriculum)
        db.session.commit()
    except Exception as error:
        db.session.rollback()
        current_app.logger.exception("Curriculum deletion failed")
        flash(f"تعذر حذف المنهج: {error}", "error")
        return redirect(url_for("platform_admin.curricula"))

    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    for relative_path in relative_paths:
        target = (upload_root / relative_path).resolve()
        if target.is_relative_to(upload_root) and target.is_file():
            try:
                target.unlink()
            except OSError:
                current_app.logger.warning("Could not remove curriculum file: %s", target)

    flash(
        "تم حذف المنهج ومصادره وملفاته نهائيًا."
        if was_active
        else "تم حذف المنهج ومصادره وملفاته نهائيًا.",
        "success",
    )
    return redirect(url_for("platform_admin.curricula"))


@platform_admin_bp.post("/curricula/<int:curriculum_id>/toggle")
def toggle_curriculum(curriculum_id):
    curriculum = teacher_curricula().filter_by(id=curriculum_id).first_or_404()
    new_state = not curriculum.is_active
    if new_state:
        try:
            activate_curriculum(curriculum)
            db.session.commit()
        except Exception as error:
            db.session.rollback()
            flash(str(error), "error")
            return redirect(url_for("platform_admin.curricula"))
    else:
        curriculum.is_active = False
        for source in curriculum.sources:
            source.is_active = False

        # Do not leave the platform pointing at an older active version
        # when this curriculum is being switched off.
        remaining = Curriculum.query.filter(
            Curriculum.id != curriculum.id,
            Curriculum.subject == curriculum.subject,
            Curriculum.grade == curriculum.grade,
            Curriculum.processing_status == "ready",
        ).order_by(
            Curriculum.activated_at.desc().nullslast(),
            Curriculum.created_at.desc(),
            Curriculum.id.desc(),
        ).first()

        if remaining:
            activate_curriculum(remaining)

        db.session.commit()
    flash("تم تحديث حالة المنهج ومصادره", "success")
    return redirect(url_for("platform_admin.curricula"))


@platform_admin_bp.route("/classrooms", methods=["GET", "POST"])
def classrooms():
    form = ClassroomForm()
    if form.validate_on_submit():
        db.session.add(Classroom(teacher_id=current_user.id, name=form.name.data.strip(), grade=form.grade.data.strip(), academic_year=form.academic_year.data.strip(), whatsapp_url=(form.whatsapp_url.data or "").strip() or None))
        db.session.commit(); flash("تم إنشاء الصف", "success")
        return redirect(url_for("platform_admin.classrooms"))
    query = Classroom.query if current_user.role == "admin" else Classroom.query.filter_by(teacher_id=current_user.id)
    return render_template("platform/classrooms.html", form=form, classrooms=query.order_by(Classroom.created_at.desc()).all())


@platform_admin_bp.route("/invitations", methods=["GET", "POST"])
def invitations():
    form = InvitationForm()
    classes = Classroom.query.filter_by(teacher_id=current_user.id, is_active=True).all()
    form.classroom_id.choices = [(0, "بدون صف محدد")] + [(row.id, row.name) for row in classes]
    invitation_urls = []
    if form.validate_on_submit():
        emails = []
        for email in re.split(r"[\s,;]+", form.emails.data or ""):
            normalized = email.strip().lower()
            if normalized and normalized not in emails:
                emails.append(normalized)
        invalid = [email for email in emails if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)]
        existing = {row.email for row in User.query.filter(User.email.in_(emails)).all()} if emails else set()
        if invalid:
            form.emails.errors.append("بعض العناوين غير صالحة: " + "، ".join(invalid[:5]))
        else:
            for email in emails:
                if email in existing:
                    continue
                invitation, token = StudentInvitation.create(current_user.id, email, form.classroom_id.data or None, form.valid_days.data)
                db.session.add(invitation)
                invitation_urls.append({"email": email, "url": url_for("auth.register_invitation", token=token, _external=True)})
            db.session.commit()
            flash(f"تم إنشاء {len(invitation_urls)} دعوة خاصة، وتجاوز {len(existing)} حسابًا موجودًا.", "success")
    query = StudentInvitation.query if current_user.role == "admin" else StudentInvitation.query.filter_by(teacher_id=current_user.id)
    return render_template("platform/invitations.html", form=form, invitations=query.order_by(StudentInvitation.created_at.desc()).limit(200).all(), invitation_urls=invitation_urls)


@platform_admin_bp.route("/resources", methods=["GET", "POST"])
def resources():
    form = LearningResourceForm(); form.lesson_id.choices = lesson_choices()
    if form.validate_on_submit():
        try:
            owned_lesson_or_404(form.lesson_id.data)
            original, path, relative = save_upload(form.document.data, "learning_resources", {"pdf", "doc", "docx", "png", "jpg", "jpeg"})
            resource = LearningResource(lesson_id=form.lesson_id.data, created_by_id=current_user.id, title=form.title.data.strip(), resource_type=form.resource_type.data, description=(form.description.data or "").strip() or None, original_filename=original, stored_path=relative, mime_type=form.document.data.mimetype, allow_download=form.allow_download.data, publication_status=form.publication_status.data)
            db.session.add(resource); db.session.commit(); flash("تم حفظ المحتوى التعليمي", "success")
            return redirect(url_for("platform_admin.resources"))
        except Exception as error:
            db.session.rollback(); flash(f"تعذر رفع الملف: {error}", "error")
    query = LearningResource.query if current_user.role == "admin" else LearningResource.query.filter_by(created_by_id=current_user.id)
    return render_template("platform/resources.html", form=form, resources=query.order_by(LearningResource.created_at.desc()).all())


def owned_content_or_404(model, row_id):
    row = db.session.get(model, row_id)
    if row is None:
        abort(404)
    if current_user.role != "admin" and row.created_by_id != current_user.id:
        abort(403)
    return row


@platform_admin_bp.post("/resources/<int:row_id>/toggle")
def toggle_resource(row_id):
    row = owned_content_or_404(LearningResource, row_id)
    row.publication_status = "draft" if row.publication_status == "published" else "published"
    db.session.commit()
    flash("تم تحديث ظهور الملف للطلاب.", "success")
    return redirect(url_for("platform_admin.resources"))


@platform_admin_bp.post("/resources/<int:row_id>/delete")
def delete_resource(row_id):
    row = owned_content_or_404(LearningResource, row_id)
    relative_path = row.stored_path
    db.session.delete(row)
    db.session.commit()
    if relative_path:
        target = (Path(current_app.config["UPLOAD_FOLDER"]) / relative_path).resolve()
        root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
        if target.is_relative_to(root) and target.is_file():
            target.unlink()
    flash("تم حذف الملف نهائيًا.", "success")
    return redirect(url_for("platform_admin.resources"))


@platform_admin_bp.route("/concept-maps", methods=["GET", "POST"])
def concept_maps():
    form = ConceptMapForm(); form.lesson_id.choices = lesson_choices()
    upload_form = ConceptMapUploadForm(prefix="upload"); upload_form.lesson_id.choices = lesson_choices()
    if form.validate_on_submit():
        try:
            graph = json.loads(form.nodes_json.data or "{}")
        except ValueError:
            graph = {}
        nodes_data = graph.get("nodes", []) if isinstance(graph, dict) else []
        edges_data = graph.get("edges", []) if isinstance(graph, dict) else []
        if len(nodes_data) < 2:
            form.nodes_json.errors.append("أضيفي مفهومين على الأقل داخل المصمم")
        else:
            owned_lesson_or_404(form.lesson_id.data)
            nodes_data = nodes_data[:80]
            edges_data = edges_data[:160]
            concept_map = ConceptMap(lesson_id=form.lesson_id.data, created_by_id=current_user.id, title=form.title.data.strip(), map_type=form.map_type.data, creation_method="manual", publication_status=form.publication_status.data)
            db.session.add(concept_map); db.session.flush()
            nodes = {}
            for index, item in enumerate(nodes_data):
                label = str(item.get("label", "")).strip()[:250]
                if not label: continue
                try:
                    position_x = min(max(float(item.get("x", (index % 3) * 260)), 0), 2000)
                    position_y = min(max(float(item.get("y", (index // 3) * 150)), 0), 2000)
                except (TypeError, ValueError):
                    position_x, position_y = (index % 3) * 260, (index // 3) * 150
                node = ConceptMapNode(concept_map_id=concept_map.id, label=label, description=str(item.get("description", "")).strip()[:2000] or None, position_x=position_x, position_y=position_y)
                db.session.add(node); db.session.flush(); nodes[str(item.get("key", index))] = node
            for item in edges_data:
                source, target = nodes.get(str(item.get("source"))), nodes.get(str(item.get("target")))
                if source and target and source.id != target.id:
                    db.session.add(ConceptMapEdge(concept_map_id=concept_map.id, source_node_id=source.id, target_node_id=target.id, label=str(item.get("label", ""))[:150] or None))
            db.session.commit(); flash("تم إنشاء الخريطة المفاهيمية", "success")
            return redirect(url_for("platform_admin.concept_maps"))
    query = ConceptMap.query if current_user.role == "admin" else ConceptMap.query.filter_by(created_by_id=current_user.id)
    return render_template("platform/concept_maps.html", form=form, upload_form=upload_form, maps=query.order_by(ConceptMap.created_at.desc()).all())


@platform_admin_bp.post("/concept-maps/upload")
def upload_concept_map():
    form = ConceptMapUploadForm(prefix="upload"); form.lesson_id.choices = lesson_choices()
    if not form.validate_on_submit():
        flash("راجعي بيانات خريطة الرفع وصيغة الملف.", "error")
        return redirect(url_for("platform_admin.concept_maps"))
    owned_lesson_or_404(form.lesson_id.data)
    original, path, relative = save_upload(form.document.data, "concept_maps", {"pdf", "png", "jpg", "jpeg", "webp"})
    row = ConceptMap(lesson_id=form.lesson_id.data, created_by_id=current_user.id, title=form.title.data.strip(), map_type="uploaded", creation_method="upload", publication_status=form.publication_status.data, original_filename=original, stored_path=relative, mime_type=form.document.data.mimetype)
    db.session.add(row); db.session.commit()
    flash("تم رفع الخريطة الجاهزة.", "success")
    return redirect(url_for("platform_admin.concept_maps"))


@platform_admin_bp.post("/concept-maps/generate")
def generate_concept_map():
    lesson = owned_lesson_or_404(request.form.get("lesson_id", type=int))
    try:
        payload = generate_concept_map_draft(lesson, request.form.get("map_type", "concept"))
        row = ConceptMap(
            lesson_id=lesson.id,
            created_by_id=current_user.id,
            title=payload.get("title") or f"خريطة {lesson.title}",
            map_type=request.form.get("map_type", "concept"),
            creation_method="ai",
            publication_status="draft",
        )
        db.session.add(row); db.session.flush()
        node_by_key = {}
        for index, item in enumerate(payload["nodes"]):
            node = ConceptMapNode(
                concept_map_id=row.id,
                label=str(item.get("label", "")).strip()[:250],
                description=str(item.get("description", "")).strip() or None,
                position_x=(index % 3) * 260,
                position_y=(index // 3) * 150,
            )
            if not node.label:
                continue
            db.session.add(node); db.session.flush()
            node_by_key[str(item.get("key"))] = node
        for edge in payload["edges"]:
            source = node_by_key.get(str(edge.get("source")))
            target = node_by_key.get(str(edge.get("target")))
            if source and target and source.id != target.id:
                db.session.add(ConceptMapEdge(concept_map_id=row.id, source_node_id=source.id, target_node_id=target.id, label=str(edge.get("label", ""))[:150] or None))
        db.session.commit()
        flash("أنشأ AI خريطة كمسودة. راجعيها قبل نشرها.", "success")
    except Exception as error:
        db.session.rollback()
        current_app.logger.exception("Concept map AI generation failed")
        flash(f"تعذر إنشاء الخريطة: {error}", "error")
    return redirect(url_for("platform_admin.concept_maps"))


@platform_admin_bp.post("/concept-maps/<int:row_id>/toggle")
def toggle_concept_map(row_id):
    row = owned_content_or_404(ConceptMap, row_id)
    row.publication_status = "draft" if row.publication_status == "published" else "published"
    db.session.commit()
    flash("تم تحديث ظهور الخريطة للطلاب.", "success")
    return redirect(url_for("platform_admin.concept_maps"))


@platform_admin_bp.route("/characters", methods=["GET", "POST"])
def characters():
    form = HistoricalCharacterForm(); form.lesson_id.choices = lesson_choices()
    if form.validate_on_submit():
        db.session.add(HistoricalCharacter(lesson_id=form.lesson_id.data, created_by_id=current_user.id, name=form.name.data.strip(), period=(form.period.data or "").strip() or None, summary=form.summary.data.strip(), key_events=(form.key_events.data or "").strip() or None, clues=(form.clues.data or "").strip() or None, source_notes=(form.source_notes.data or "").strip() or None, publication_status=form.publication_status.data))
        db.session.commit(); flash("تم حفظ الشخصية التاريخية", "success")
        return redirect(url_for("platform_admin.characters"))
    query = HistoricalCharacter.query if current_user.role == "admin" else HistoricalCharacter.query.filter_by(created_by_id=current_user.id)
    return render_template("platform/characters.html", form=form, characters=query.order_by(HistoricalCharacter.created_at.desc()).all())


@platform_admin_bp.post("/characters/generate")
def generate_characters():
    lesson = db.session.get(Lesson, request.form.get("lesson_id", type=int))
    if lesson is None or lesson not in teacher_lessons():
        abort(404)
    try:
        drafts, citations = generate_character_drafts(lesson)
        created = 0
        for item in drafts:
            name = str(item.get("name", "")).strip()
            summary = str(item.get("summary", "")).strip()
            if not name or not summary or HistoricalCharacter.query.filter_by(lesson_id=lesson.id, name=name).first():
                continue
            clues = item.get("who_am_i_clues") or []
            notes = "\n".join(citations)
            db.session.add(HistoricalCharacter(
                lesson_id=lesson.id,
                created_by_id=current_user.id,
                name=name[:200],
                period=str(item.get("period", "")).strip()[:150] or None,
                summary=summary[:5000],
                key_events="\n".join(str(event) for event in (item.get("key_events") or []))[:5000] or None,
                source_notes=notes[:2000],
                clues="\n".join(str(clue) for clue in clues)[:3000] or None,
                publication_status="draft",
                is_ai_generated=True,
            ))
            created += 1
        db.session.commit()
        flash(f"تم حفظ {created} شخصية كمسودات للمراجعة.", "success")
    except Exception as error:
        db.session.rollback()
        current_app.logger.exception("Character AI generation failed")
        flash(f"تعذر استخراج الشخصيات: {error}", "error")
    return redirect(url_for("platform_admin.characters"))


@platform_admin_bp.route("/characters/<int:row_id>/edit", methods=["GET", "POST"])
def edit_character(row_id):
    row = owned_content_or_404(HistoricalCharacter, row_id)
    form = HistoricalCharacterForm(obj=row)
    form.lesson_id.choices = lesson_choices()
    if form.validate_on_submit():
        row.lesson_id = form.lesson_id.data
        row.name = form.name.data.strip()
        row.period = (form.period.data or "").strip() or None
        row.summary = form.summary.data.strip()
        row.key_events = (form.key_events.data or "").strip() or None
        row.clues = (form.clues.data or "").strip() or None
        row.source_notes = (form.source_notes.data or "").strip() or None
        row.publication_status = form.publication_status.data
        db.session.commit()
        flash("تمت مراجعة الشخصية وحفظها.", "success")
        return redirect(url_for("platform_admin.characters"))
    return render_template("platform/edit_character.html", form=form, character=row)


@platform_admin_bp.post("/characters/<int:row_id>/toggle")
def toggle_character(row_id):
    row = owned_content_or_404(HistoricalCharacter, row_id)
    row.publication_status = "draft" if row.publication_status == "published" else "published"
    db.session.commit()
    flash("تم تحديث ظهور الشخصية للطلاب.", "success")
    return redirect(url_for("platform_admin.characters"))


@platform_admin_bp.route("/settings", methods=["GET", "POST"])
def settings():
    row = PlatformSettings.get_or_create(); form = PlatformSettingsForm(obj=row)
    if form.validate_on_submit():
        whatsapp_value = (form.whatsapp_url.data or "").strip()
        if whatsapp_value:
            compact_whatsapp = re.sub(r"[\\s\\-()]+", "", whatsapp_value)
            if compact_whatsapp.startswith("00"):
                compact_whatsapp = compact_whatsapp[2:]
            if compact_whatsapp.startswith("+"):
                compact_whatsapp = compact_whatsapp[1:]
            if compact_whatsapp.isdigit():
                if compact_whatsapp.startswith("0"):
                    compact_whatsapp = "970" + compact_whatsapp[1:]
                whatsapp_value = f"https://wa.me/{compact_whatsapp}"
        row.platform_name = form.platform_name.data
        row.tagline = form.tagline.data
        row.whatsapp_url = whatsapp_value or None
        row.support_email = form.support_email.data
        db.session.commit(); flash("تم حفظ إعدادات المنصة", "success")
        return redirect(url_for("platform_admin.settings"))
    return render_template("platform/settings.html", form=form)


@platform_admin_bp.get("/analytics")
def analytics():
    """Teacher-facing learning analytics, aggregated and per student."""
    worksheet_query = Worksheet.query
    if current_user.role != "admin":
        worksheet_query = worksheet_query.filter_by(created_by_id=current_user.id)
    worksheet_ids = [row.id for row in worksheet_query.all()]
    attempts = []
    if worksheet_ids:
        attempts = WorksheetAttempt.query.filter(
            WorksheetAttempt.worksheet_id.in_(worksheet_ids),
            WorksheetAttempt.submitted_at.isnot(None),
        ).all()

    student_ids = {attempt.student_id for attempt in attempts}
    classroom_query = Classroom.query
    if current_user.role != "admin":
        classroom_query = classroom_query.filter_by(teacher_id=current_user.id)
    classrooms = classroom_query.all()
    for classroom in classrooms:
        student_ids.update(enrollment.student_id for enrollment in classroom.enrollments)

    students = User.query.filter(User.id.in_(student_ids)).all() if student_ids else []
    rows = []
    for student in students:
        student_attempts = [attempt for attempt in attempts if attempt.student_id == student.id]
        percentages = [attempt.percentage for attempt in student_attempts]
        mastery_rows = ConceptMastery.query.filter_by(student_id=student.id).all()
        challenges = ChallengeSession.query.filter_by(student_id=student.id, status="completed").all()
        evaluated_messages = TutorMessage.query.join(TutorMessage.conversation).filter(
            TutorMessage.conversation.has(student_id=student.id),
            TutorMessage.evaluation.in_(["correct", "partially_correct", "incorrect", "needs_explanation"]),
        ).count()
        average = round(sum(percentages) / len(percentages), 1) if percentages else 0.0
        mastery_average = round(sum(item.mastery_score for item in mastery_rows) / len(mastery_rows), 1) if mastery_rows else 0.0
        activity_score = len(student_attempts) + len(challenges) + evaluated_messages
        rows.append({
            "student": student,
            "worksheet_count": len(student_attempts),
            "average": average,
            "mastery_average": mastery_average,
            "challenge_count": len(challenges),
            "tutor_interactions": evaluated_messages,
            "activity_score": activity_score,
            "needs_support": (bool(percentages) and average < 50) or (bool(mastery_rows) and mastery_average < 50),
        })
    rows.sort(key=lambda item: (item["activity_score"], item["average"]), reverse=True)
    class_percentages = [attempt.percentage for attempt in attempts]
    overview = {
        "students": len(students),
        "worksheets": len(worksheet_ids),
        "submissions": len(attempts),
        "average": round(sum(class_percentages) / len(class_percentages), 1) if class_percentages else 0.0,
        "support_count": sum(1 for row in rows if row["needs_support"]),
    }
    return render_template("platform/analytics.html", rows=rows, overview=overview)


@platform_admin_bp.route("/honor-board", methods=["GET", "POST"])
def honor_board():
    classrooms = Classroom.query.filter_by(teacher_id=current_user.id, is_active=True).all()
    student_ids = {enrollment.student_id for classroom in classrooms for enrollment in classroom.enrollments}
    students = User.query.filter(User.id.in_(student_ids)).order_by(User.full_name).all() if student_ids else []
    if request.method == "POST":
        student_id = request.form.get("student_id", type=int)
        if student_id not in student_ids:
            abort(403)
        entry = HonorBoardEntry(teacher_id=current_user.id, student_id=student_id, category=request.form.get("category", "teacher_choice")[:50], note=(request.form.get("note") or "").strip()[:300] or None, period_label=(request.form.get("period_label") or "").strip()[:100] or None)
        db.session.add(entry); db.session.commit(); flash("تمت إضافة الطالبة إلى لوحة الشرف.", "success")
        return redirect(url_for("platform_admin.honor_board"))
    entries = HonorBoardEntry.query.filter_by(teacher_id=current_user.id, is_active=True).order_by(HonorBoardEntry.created_at.desc()).all()
    return render_template("platform/honor_board.html", students=students, entries=entries)


@platform_admin_bp.post("/honor-board/<int:entry_id>/remove")
def remove_honor_entry(entry_id):
    row = HonorBoardEntry.query.filter_by(id=entry_id, teacher_id=current_user.id).first_or_404()
    row.is_active = False
    db.session.commit(); flash("تمت إزالة البطاقة من لوحة الشرف.", "success")
    return redirect(url_for("platform_admin.honor_board"))
