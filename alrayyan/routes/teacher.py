from flask import (
     Blueprint,
     current_app,
     jsonify,
     render_template,
     request,
)

from alrayyan.services.ai_teacher import ask_ai_teacher


teacher_bp = Blueprint(
    "teacher",
    __name__,
    url_prefix="/teacher",
)


@teacher_bp.get("/")
def teacher_page():
    return render_template("teacher.html")


@teacher_bp.post("/ask")
def ask_teacher():
    data = request.get_json(silent=True) or {}
    question = data.get("question", "")

    try:
        result = ask_ai_teacher(question)
        return jsonify(
            {
                "success": True,
                **result,
            }
        )

    except ValueError as error:
        return jsonify(
            {
                "success": False,
                "error": str(error),
            }
        ), 400

    except RuntimeError as error:
        current_app.logger.exception(
            "AI teacher request failed."
        )

        return jsonify(
            {
                "success": False,
                "error": str(error),
            }
        ), 502

    except Exception:
        current_app.logger.exception(
            "Unexpected AI teacher error."
        )

        return jsonify(
            {
                "success": False,
                "error": (
                    "حدث خطأ غير متوقع. "
                    "يرجى المحاولة مرة أخرى."
                ),
            }
        ), 500