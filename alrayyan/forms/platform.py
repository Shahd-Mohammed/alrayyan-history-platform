from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import BooleanField, EmailField, HiddenField, IntegerField, PasswordField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional, URL


class CurriculumUploadForm(FlaskForm):
    subject = StringField("المادة", validators=[DataRequired(), Length(max=100)])
    grade = StringField("الصف", validators=[DataRequired(), Length(max=50)])
    semester = SelectField("الفصل", choices=[("الأول", "الفصل الأول"), ("الثاني", "الفصل الثاني")])
    academic_year = StringField("العام الدراسي", validators=[DataRequired(), Length(max=30)])
    curriculum_name = StringField("اسم المنهج", validators=[DataRequired(), Length(max=200)], description="اسم تعريفي يظهر في قائمة المناهج؛ يساعدك على تمييز نسخ المنهج.")
    unit_title = StringField("اسم الوحدة (اختياري)", validators=[Optional(), Length(max=200)], description="يُستخدم كعنوان بديل فقط إذا لم يتعرف النظام على الوحدات في الملف.")
    lesson_title = StringField("اسم الدرس (اختياري)", validators=[Optional(), Length(max=250)], description="يُستخدم كعنوان بديل فقط إذا لم يتعرف النظام على الدروس في الملف.")
    source_title = StringField("اسم المصدر", validators=[DataRequired(), Length(max=250)], description="اسم الكتاب أو الملزمة كما سيظهر في سجل مصادر المنهج.")
    source_type = SelectField("نوع المصدر", choices=[("official_book", "الكتاب الرسمي"), ("supporting_book", "المصادر المساندة"), ("review_notes", "الملازم والمراجعات")])
    document = FileField("ملف المنهج", validators=[FileRequired(), FileAllowed(["pdf", "docx"], "المتاح PDF أو DOCX فقط")])
    submit = SubmitField("رفع وتجهيز المصدر")


class ClassroomForm(FlaskForm):
    name = StringField("اسم الصف أو الشعبة", validators=[DataRequired(), Length(max=120)])
    grade = StringField("الصف الدراسي", validators=[DataRequired(), Length(max=50)])
    academic_year = StringField("العام الدراسي", validators=[DataRequired(), Length(max=30)])
    whatsapp_url = StringField("رابط مجموعة واتساب", validators=[Optional(), URL(), Length(max=500)])
    submit = SubmitField("حفظ الصف")


class InvitationForm(FlaskForm):
    emails = TextAreaField(
        "بريد الطالبات",
        validators=[DataRequired(), Length(max=20000)],
        description="بريد واحد في كل سطر، أو افصلي بينها بفاصلة.",
    )
    classroom_id = SelectField("الصف", coerce=int, validators=[Optional()])
    valid_days = IntegerField("صلاحية الدعوة بالأيام", default=7, validators=[DataRequired(), NumberRange(min=1, max=30)])
    submit = SubmitField("إنشاء رابط الدعوة")


class InvitationRegistrationForm(FlaskForm):
    full_name = StringField("الاسم الكامل", validators=[DataRequired(), Length(min=2, max=150)])
    password = PasswordField("كلمة المرور", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField("تأكيد كلمة المرور", validators=[DataRequired(), EqualTo("password", message="كلمتا المرور غير متطابقتين")])
    submit = SubmitField("تفعيل حسابي")


class PlatformSettingsForm(FlaskForm):
    platform_name = StringField("اسم المنصة", validators=[DataRequired(), Length(max=150)])
    tagline = StringField("العبارة التعريفية", validators=[DataRequired(), Length(max=250)])
    whatsapp_url = StringField("رقم واتساب المنصة", validators=[Optional(), Length(max=500)], description="أدخلي رقم واتساب مع مفتاح الدولة أو رابط واتساب مباشر. سيتم استخدام القيمة نفسها في أيقونة واتساب في الفوتر.")
    support_email = EmailField("بريد التواصل", validators=[Optional(), Email(), Length(max=255)])
    submit = SubmitField("حفظ الإعدادات")


class LearningResourceForm(FlaskForm):
    lesson_id = SelectField("الدرس", coerce=int, validators=[DataRequired()])
    resource_type = SelectField("نوع المحتوى", choices=[("lesson_summary", "ملخص الدرس"), ("review", "مراجعة"), ("class_activity", "نشاط صفي"), ("homework", "واجب"), ("slides", "شرائح تعليمية"), ("supporting_material", "ملف مساند")])
    title = StringField("العنوان", validators=[DataRequired(), Length(max=250)])
    description = TextAreaField("وصف مختصر", validators=[Optional(), Length(max=1500)])
    document = FileField("الملف", validators=[FileRequired(), FileAllowed(["pdf", "doc", "docx", "png", "jpg", "jpeg"], "صيغة الملف غير مدعومة")])
    allow_download = BooleanField("السماح بالتنزيل", default=True)
    publication_status = SelectField("الحالة", choices=[("draft", "مسودة"), ("published", "منشور")])
    submit = SubmitField("حفظ المحتوى")


class ConceptMapForm(FlaskForm):
    lesson_id = SelectField("الدرس", coerce=int, validators=[DataRequired()])
    title = StringField("عنوان الخريطة", validators=[DataRequired(), Length(max=250)])
    map_type = SelectField("نوع الخريطة", choices=[("concept", "مفهوم وفروع"), ("cause_effect", "أسباب ونتائج"), ("comparison", "مقارنة"), ("timeline", "تسلسل زمني")])
    nodes_json = HiddenField("بيانات الخريطة", validators=[Optional(), Length(max=50000)])
    publication_status = SelectField("الحالة", choices=[("draft", "مسودة"), ("published", "منشورة")])
    submit = SubmitField("إنشاء الخريطة")


class ConceptMapUploadForm(FlaskForm):
    lesson_id = SelectField("الدرس", coerce=int, validators=[DataRequired()])
    title = StringField("عنوان الخريطة", validators=[DataRequired(), Length(max=250)])
    document = FileField("ملف الخريطة", validators=[FileRequired(), FileAllowed(["pdf", "png", "jpg", "jpeg", "webp"], "المتاح PDF أو صورة فقط")])
    publication_status = SelectField("الحالة", choices=[("draft", "مسودة"), ("published", "منشورة")])
    submit = SubmitField("رفع الخريطة")


class HistoricalCharacterForm(FlaskForm):
    lesson_id = SelectField("الدرس", coerce=int, validators=[DataRequired()])
    name = StringField("اسم الشخصية", validators=[DataRequired(), Length(max=200)])
    period = StringField("الفترة الزمنية", validators=[Optional(), Length(max=150)])
    summary = TextAreaField("التعريف والدور", validators=[DataRequired(), Length(max=5000)])
    key_events = TextAreaField("أهم الأحداث", validators=[Optional(), Length(max=5000)])
    clues = TextAreaField("تلميحات لعبة من أنا؟", validators=[Optional(), Length(max=3000)], description="تلميح واحد في كل سطر، دون اسم المصدر.")
    source_notes = TextAreaField("ملاحظات المصدر", validators=[Optional(), Length(max=2000)])
    publication_status = SelectField("الحالة", choices=[("draft", "مسودة"), ("published", "منشورة")])
    submit = SubmitField("حفظ الشخصية")
