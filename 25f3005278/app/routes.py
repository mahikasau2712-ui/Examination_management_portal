"""MVC controllers: routes coordinate request validation, ORM operations and views."""
from datetime import datetime, date, time
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_

from . import db
from .models import Booking, Course, Examination, ExamSlot, Rubric, RubricScore, User
from .schemas import ValidationError, number, optional_datetime, required, valid_email

main_bp = Blueprint("main", __name__)
auth_bp = Blueprint("auth", __name__)
admin_bp = Blueprint("admin", __name__)
examiner_bp = Blueprint("examiner", __name__)
student_bp = Blueprint("student", __name__)


def role_required(*roles):
    """MVC access-control wrapper; controllers enforce role-specific access."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles or not current_user.active:
                abort(403)
            if current_user.role == "examiner" and not current_user.approved:
                flash("Your examiner account is awaiting administrator approval.", "warning")
                return redirect(url_for("main.index"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def parse_date(value):
    return date.fromisoformat(value)


def parse_time(value):
    return time.fromisoformat(value)


def report_error(error):
    db.session.rollback()
    flash(str(error), "danger")


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        endpoint = {"admin": "admin.dashboard", "examiner": "examiner.dashboard", "student": "student.dashboard"}.get(current_user.role)
        if endpoint:
            return redirect(url_for(endpoint))
    return render_template("index.html", exams=Examination.query.filter_by(status="Booking Open").all())


@main_bp.route("/examinations")
def examinations():
    query = Examination.query.join(Course)
    search = request.args.get("q", "").strip()
    course_id = request.args.get("course", "")
    exam_type = request.args.get("type", "")
    if search:
        query = query.filter(or_(Examination.name.ilike(f"%{search}%"), Course.name.ilike(f"%{search}%"), Course.code.ilike(f"%{search}%")))
    if course_id.isdigit():
        query = query.filter(Examination.course_id == int(course_id))
    if exam_type:
        query = query.filter(Examination.exam_type == exam_type)
    if not (current_user.is_authenticated and current_user.role == "admin"):
        query = query.filter(Examination.status.in_(["Booking Open", "Slot Creation", "Closed", "Completed"]))
    return render_template("examinations.html", exams=query.order_by(Examination.name).all(), courses=Course.query.filter_by(active=True).all())


@auth_bp.route("/register/<role>", methods=["GET", "POST"])
def register(role):
    if role not in ("student", "examiner"):
        abort(404)
    if request.method == "POST":
        try:
            required(request.form, "name", "email", "password")
            email = request.form["email"].strip().lower()
            if not valid_email(email):
                raise ValidationError("Enter a valid email address.")
            if len(request.form["password"]) < 8:
                raise ValidationError("Password must contain at least 8 characters.")
            if User.query.filter_by(email=email).first():
                raise ValidationError("An account with that email already exists.")
            user = User(name=request.form["name"].strip(), email=email, role=role,
                        department=request.form.get("department", "").strip(),
                        phone=request.form.get("phone", "").strip(), approved=(role == "student"), active=True)
            user.set_password(request.form["password"])
            db.session.add(user)
            db.session.commit()
            flash("Account created. Examiner accounts need administrator approval before access.", "success")
            return redirect(url_for("auth.login"))
        except ValidationError as error:
            report_error(error)
    return render_template("auth/register.html", role=role)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and user.active and user.check_password(request.form.get("password", "")):
            login_user(user)
            if user.role == "examiner" and not user.approved:
                logout_user()
                flash("Your examiner account is awaiting administrator approval.", "warning")
                return redirect(url_for("auth.login"))
            flash(f"Welcome, {user.name}.", "success")
            return redirect(url_for("main.index"))
        flash("Email or password is incorrect, or this account is inactive.", "danger")
    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.index"))


@admin_bp.route("/")
@role_required("admin")
def dashboard():
    stats = {"courses": Course.query.count(), "exams": Examination.query.count(),
             "examiners": User.query.filter_by(role="examiner").count(), "students": User.query.filter_by(role="student").count(),
             "slots": ExamSlot.query.count(), "bookings": Booking.query.count()}
    return render_template("admin/dashboard.html", stats=stats,
                           pending=User.query.filter_by(role="examiner", approved=False).order_by(User.created_at).all(),
                           exams=Examination.query.order_by(Examination.id.desc()).limit(8).all())


@admin_bp.route("/courses", methods=["GET", "POST"])
@role_required("admin")
def courses():
    if request.method == "POST":
        try:
            required(request.form, "code", "name")
            code = request.form["code"].strip().upper()
            if Course.query.filter_by(code=code).first():
                raise ValidationError("Course code must be unique.")
            db.session.add(Course(code=code, name=request.form["name"].strip(), description=request.form.get("description", "").strip()))
            db.session.commit()
            flash("Course created.", "success")
        except ValidationError as error:
            report_error(error)
    return render_template("admin/courses.html", courses=Course.query.order_by(Course.code).all())


@admin_bp.route("/courses/<int:course_id>/edit", methods=["POST"])
@role_required("admin")
def edit_course(course_id):
    course = db.get_or_404(Course, course_id)
    try:
        required(request.form, "code", "name")
        code = request.form["code"].strip().upper()
        duplicate = Course.query.filter(Course.code == code, Course.id != course.id).first()
        if duplicate:
            raise ValidationError("Course code must be unique.")
        course.code, course.name = code, request.form["name"].strip()
        course.description = request.form.get("description", "").strip()
        course.active = "active" in request.form
        db.session.commit()
        flash("Course updated.", "success")
    except ValidationError as error:
        report_error(error)
    return redirect(url_for("admin.courses"))


@admin_bp.route("/courses/<int:course_id>/delete", methods=["POST"])
@role_required("admin")
def delete_course(course_id):
    course = db.get_or_404(Course, course_id)
    if course.examinations:
        flash("A course with examinations cannot be deleted. Deactivate it instead.", "warning")
    else:
        db.session.delete(course)
        db.session.commit()
        flash("Course removed.", "success")
    return redirect(url_for("admin.courses"))


@admin_bp.route("/exams", methods=["GET", "POST"])
@role_required("admin")
def exams():
    exam = None
    if request.method == "POST":
        try:
            required(request.form, "course_id", "name", "exam_type", "duration_minutes", "max_marks")
            exam = Examination(
                course_id=number(request.form, "course_id", "Course", 1, True), name=request.form["name"].strip(),
                exam_type=request.form["exam_type"], duration_minutes=number(request.form, "duration_minutes", "Duration", 1, True),
                max_marks=number(request.form, "max_marks", "Maximum marks", 1), status=request.form.get("status", "Draft"),
                slot_start=optional_datetime(request.form, "slot_start", "Slot start"), slot_end=optional_datetime(request.form, "slot_end", "Slot end"),
                booking_start=optional_datetime(request.form, "booking_start", "Booking start"), booking_end=optional_datetime(request.form, "booking_end", "Booking end"))
            if not db.session.get(Course, exam.course_id):
                raise ValidationError("Choose an existing course.")
            db.session.add(exam)
            db.session.commit()
            flash("Examination created.", "success")
        except (ValidationError, ValueError) as error:
            report_error(error)
    return render_template("admin/exams.html", exams=Examination.query.order_by(Examination.id.desc()).all(), courses=Course.query.filter_by(active=True).all(), users=User.query.filter_by(role="examiner", approved=True, active=True).all())


@admin_bp.route("/exams/<int:exam_id>/edit", methods=["POST"])
@role_required("admin")
def edit_exam(exam_id):
    exam = db.get_or_404(Examination, exam_id)
    try:
        required(request.form, "name", "duration_minutes", "max_marks")
        exam.name = request.form["name"].strip()
        exam.duration_minutes = number(request.form, "duration_minutes", "Duration", 1, True)
        exam.max_marks = number(request.form, "max_marks", "Maximum marks", 1)
        exam.status = request.form.get("status", exam.status)
        for field in ("slot_start", "slot_end", "booking_start", "booking_end"):
            setattr(exam, field, optional_datetime(request.form, field, field.replace("_", " ").title()))
        exam.results_published = "results_published" in request.form
        db.session.commit()
        flash("Examination schedule and settings updated.", "success")
    except (ValidationError, ValueError) as error:
        report_error(error)
    return redirect(url_for("admin.exams"))


@admin_bp.route("/exams/<int:exam_id>/delete", methods=["POST"])
@role_required("admin")
def delete_exam(exam_id):
    exam = db.get_or_404(Examination, exam_id)
    # Keep historical examination data available to the admin. Exams with bookings are closed instead of hard-deleted.
    if Booking.query.join(ExamSlot).filter(ExamSlot.examination_id == exam.id).count():
        exam.status = "Closed"
        db.session.commit()
        flash("This examination has booking history, so it was closed and retained for historical records.", "warning")
        return redirect(url_for("admin.exams"))
    db.session.delete(exam)
    db.session.commit()
    flash("Examination and associated slot history removed.", "success")
    return redirect(url_for("admin.exams"))


@admin_bp.route("/exams/<int:exam_id>/rubrics", methods=["GET", "POST"])
@role_required("admin")
def rubrics(exam_id):
    exam = db.get_or_404(Examination, exam_id)
    if request.method == "POST":
        try:
            required(request.form, "criterion", "max_marks")
            max_marks = number(request.form, "max_marks", "Criterion maximum marks", 0.01)
            if sum(row.max_marks for row in exam.rubrics) + max_marks > exam.max_marks:
                raise ValidationError("Total rubric marks cannot exceed the examination maximum.")
            db.session.add(Rubric(examination=exam, criterion=request.form["criterion"].strip(), max_marks=max_marks,
                                  weightage=number(request.form, "weightage", "Weightage", 0), description=request.form.get("description", "").strip()))
            db.session.commit()
            flash("Rubric criterion added.", "success")
        except ValidationError as error:
            report_error(error)
    return render_template("admin/rubrics.html", exam=exam)


@admin_bp.route("/rubrics/<int:rubric_id>/delete", methods=["POST"])
@role_required("admin")
def delete_rubric(rubric_id):
    row = db.get_or_404(Rubric, rubric_id)
    exam_id = row.examination_id
    db.session.delete(row)
    db.session.commit()
    flash("Rubric criterion removed.", "success")
    return redirect(url_for("admin.rubrics", exam_id=exam_id))


@admin_bp.route("/examiners")
@role_required("admin")
def examiners():
    return render_template("admin/examiners.html", users=User.query.filter_by(role="examiner").order_by(User.name).all())


@admin_bp.route("/examiners/<int:user_id>/status", methods=["POST"])
@role_required("admin")
def examiner_status(user_id):
    user = db.get_or_404(User, user_id)
    if user.role != "examiner":
        abort(404)
    action = request.form.get("action")
    if action == "approve":
        user.approved = True
    if action == "deactivate":
        user.active = False
    elif action == "activate":
        user.active = True
    db.session.commit()
    flash("Examiner account updated.", "success")
    return redirect(url_for("admin.examiners"))


@admin_bp.route("/slots")
@role_required("admin")
def slots():
    return render_template("admin/slots.html", slots=ExamSlot.query.order_by(ExamSlot.date, ExamSlot.start_time).all(), examiners=User.query.filter_by(role="examiner", approved=True, active=True).all())


@admin_bp.route("/slots/<int:slot_id>/assign", methods=["POST"])
@role_required("admin")
def reassign_slot(slot_id):
    slot = db.get_or_404(ExamSlot, slot_id)
    examiner = db.session.get(User, request.form.get("examiner_id", type=int))
    if not examiner or examiner.role != "examiner" or not examiner.approved or not examiner.active:
        flash("Select an active approved examiner.", "danger")
    else:
        slot.examiner_id = examiner.id
        db.session.commit()
        flash("Examiner assignment changed.", "success")
    return redirect(url_for("admin.slots"))


@admin_bp.route("/bookings")
@role_required("admin")
def bookings():
    query = Booking.query.join(User, Booking.student_id == User.id).join(ExamSlot).join(Examination)
    search = request.args.get("q", "").strip()
    if search:
        id_match = Booking.id == int(search) if search.isdigit() else False
        query = query.filter(or_(User.name.ilike(f"%{search}%"), User.email.ilike(f"%{search}%"), Examination.name.ilike(f"%{search}%"), id_match))
    return render_template("admin/bookings.html", bookings=query.order_by(Booking.booked_at.desc()).all(), slots=ExamSlot.query.all(), search=search)


@admin_bp.route("/bookings/<int:booking_id>/reschedule", methods=["POST"])
@role_required("admin")
def reschedule(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    target = db.session.get(ExamSlot, request.form.get("slot_id", type=int))
    if not target or target.examination_id != booking.slot.examination_id:
        flash("Choose a slot for the same examination.", "danger")
    elif target.id != booking.slot_id and target.seats_left < 1:
        flash("That slot is full.", "danger")
    elif Booking.query.filter_by(student_id=booking.student_id, slot_id=target.id, status="Booked").filter(Booking.id != booking.id).first():
        flash("This student already has a booking in that slot.", "danger")
    else:
        booking.slot_id = target.id
        booking.status = "Booked"
        db.session.commit()
        flash("Booking rescheduled.", "success")
    return redirect(url_for("admin.bookings"))


@admin_bp.route("/search")
@role_required("admin")
def search():
    term = request.args.get("q", "").strip()
    students_query = User.query.filter_by(role="student")
    staff_query = User.query.filter_by(role="examiner")
    exams_query = Examination.query
    if term:
        numeric_id = int(term) if term.isdigit() else None
        students_query = students_query.filter(or_(User.name.ilike(f"%{term}%"), User.email.ilike(f"%{term}%"), User.id == numeric_id))
        staff_query = staff_query.filter(or_(User.name.ilike(f"%{term}%"), User.email.ilike(f"%{term}%"), User.id == numeric_id))
        exams_query = exams_query.filter(or_(Examination.name.ilike(f"%{term}%"), Examination.id == numeric_id))
    students, staff, exams = students_query.order_by(User.name).all(), staff_query.order_by(User.name).all(), exams_query.order_by(Examination.name).all()
    return render_template("admin/search.html", q=term, students=students, staff=staff, exams=exams)


@examiner_bp.route("/")
@role_required("examiner")
def dashboard():
    slots = ExamSlot.query.filter_by(examiner_id=current_user.id).order_by(ExamSlot.date, ExamSlot.start_time).all()
    exam_ids = {slot.examination_id for slot in slots}
    exams = Examination.query.filter(Examination.id.in_(exam_ids)).all() if exam_ids else []
    bookings = Booking.query.join(ExamSlot).filter(ExamSlot.examiner_id == current_user.id, Booking.status == "Booked").all()
    pending = [b for b in bookings if b.marks is None]
    return render_template("examiner/dashboard.html", slots=slots, exams=exams, bookings=bookings, pending=pending)


@examiner_bp.route("/slots", methods=["GET", "POST"])
@role_required("examiner")
def create_slot():
    assigned = Examination.query.join(ExamSlot).filter(ExamSlot.examiner_id == current_user.id).all()
    # Slot creation also offered for exams with an open slot window but no slots yet.
    window_exams = Examination.query.filter(Examination.status == "Slot Creation").all()
    exams = {e.id: e for e in assigned + window_exams}.values()
    if request.method == "POST":
        try:
            required(request.form, "examination_id", "date", "start_time", "end_time", "capacity")
            exam = db.session.get(Examination, number(request.form, "examination_id", "Examination", 1, True))
            now = datetime.utcnow()
            if not exam or exam.status != "Slot Creation":
                raise ValidationError("Slots can only be created while the admin has opened the slot-creation period.")
            if exam.slot_start and now < exam.slot_start or exam.slot_end and now > exam.slot_end:
                raise ValidationError("The slot-creation time window is closed.")
            start, end = parse_time(request.form["start_time"]), parse_time(request.form["end_time"])
            if end <= start:
                raise ValidationError("End time must be after start time.")
            slot = ExamSlot(examination=exam, examiner_id=current_user.id, date=parse_date(request.form["date"]), start_time=start, end_time=end,
                            capacity=number(request.form, "capacity", "Capacity", 1, True))
            db.session.add(slot)
            db.session.commit()
            flash("Examination slot created.", "success")
        except (ValidationError, ValueError) as error:
            report_error(error)
    return render_template("examiner/slots.html", exams=exams, slots=ExamSlot.query.filter_by(examiner_id=current_user.id).order_by(ExamSlot.date).all())


@examiner_bp.route("/slots/<int:slot_id>/edit", methods=["POST"])
@role_required("examiner")
def edit_slot(slot_id):
    slot = db.get_or_404(ExamSlot, slot_id)
    if slot.examiner_id != current_user.id:
        abort(403)
    if slot.booked_count or slot.examination.status != "Slot Creation":
        flash("A slot can only be edited before student booking starts and before it has bookings.", "warning")
        return redirect(url_for("examiner.create_slot"))
    try:
        start, end = parse_time(request.form["start_time"]), parse_time(request.form["end_time"])
        if end <= start:
            raise ValidationError("End time must be after start time.")
        slot.date, slot.start_time, slot.end_time = parse_date(request.form["date"]), start, end
        slot.capacity = number(request.form, "capacity", "Capacity", 1, True)
        db.session.commit()
        flash("Slot updated.", "success")
    except (ValidationError, ValueError, KeyError) as error:
        report_error(error if isinstance(error, ValidationError) else ValidationError("Enter a valid date, time and capacity."))
    return redirect(url_for("examiner.create_slot"))


@examiner_bp.route("/slots/<int:slot_id>/delete", methods=["POST"])
@role_required("examiner")
def delete_slot(slot_id):
    slot = db.get_or_404(ExamSlot, slot_id)
    if slot.examiner_id != current_user.id:
        abort(403)
    if slot.booked_count or slot.examination.status != "Slot Creation":
        flash("Only unbooked slots can be removed before booking starts.", "warning")
    else:
        db.session.delete(slot)
        db.session.commit()
        flash("Slot removed.", "success")
    return redirect(url_for("examiner.create_slot"))


@examiner_bp.route("/bookings")
@role_required("examiner")
def my_bookings():
    bookings = Booking.query.join(ExamSlot).filter(ExamSlot.examiner_id == current_user.id).order_by(Booking.booked_at.desc()).all()
    return render_template("examiner/bookings.html", bookings=bookings)


@examiner_bp.route("/bookings/<int:booking_id>/evaluate", methods=["GET", "POST"])
@role_required("examiner")
def evaluate(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    if booking.slot.examiner_id != current_user.id or booking.status != "Booked":
        abort(403)
    exam = booking.slot.examination
    if request.method == "POST":
        try:
            scores = []
            for rubric in exam.rubrics:
                mark = number(request.form, f"rubric_{rubric.id}", rubric.criterion, 0)
                if mark > rubric.max_marks:
                    raise ValidationError(f"{rubric.criterion} cannot exceed {rubric.max_marks:g} marks.")
                scores.append((rubric, mark))
            total = sum(mark for _, mark in scores) if scores else number(request.form, "marks", "Marks", 0)
            if total > exam.max_marks:
                raise ValidationError(f"Total marks cannot exceed {exam.max_marks:g}.")
            if not scores and not exam.rubrics:
                raise ValidationError("Ask the administrator to add a rubric before evaluating this examination.")
            booking.scores.clear()
            for rubric, mark in scores:
                booking.scores.append(RubricScore(rubric=rubric, marks=mark))
            booking.marks = total
            booking.remarks = request.form.get("remarks", "").strip()
            booking.evaluated_at = datetime.utcnow()
            booking.status = "Completed"
            db.session.commit()
            flash("Evaluation saved. The student can see it after results are published.", "success")
            return redirect(url_for("examiner.my_bookings"))
        except ValidationError as error:
            report_error(error)
    return render_template("examiner/evaluate.html", booking=booking, exam=exam)


@student_bp.route("/")
@role_required("student")
def dashboard():
    bookings = Booking.query.filter_by(student_id=current_user.id).order_by(Booking.booked_at.desc()).all()
    exams = Examination.query.filter(Examination.status.in_(["Booking Open", "Slot Creation", "Closed", "Completed"])).order_by(Examination.name).all()
    return render_template("student/dashboard.html", bookings=bookings, exams=exams)


@student_bp.route("/book/<int:slot_id>", methods=["POST"])
@role_required("student")
def book(slot_id):
    slot = db.get_or_404(ExamSlot, slot_id)
    exam = slot.examination
    now = datetime.utcnow()
    if exam.status != "Booking Open" or (exam.booking_start and now < exam.booking_start) or (exam.booking_end and now > exam.booking_end):
        flash("Booking is currently closed for this examination.", "warning")
    elif slot.seats_left < 1:
        slot.status = "Full"
        db.session.commit()
        flash("This slot is full.", "warning")
    elif Booking.query.join(ExamSlot).filter(Booking.student_id == current_user.id, ExamSlot.examination_id == exam.id, Booking.status.in_(["Booked", "Completed"])).first():
        flash("You already have a booking for this examination.", "warning")
    else:
        db.session.add(Booking(student_id=current_user.id, slot=slot))
        if slot.booked_count >= slot.capacity:
            slot.status = "Full"
        db.session.commit()
        flash("Slot booked successfully.", "success")
    return redirect(request.referrer or url_for("student.dashboard"))


@student_bp.route("/bookings/<int:booking_id>/cancel", methods=["POST"])
@role_required("student")
def cancel(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    if booking.student_id != current_user.id:
        abort(403)
    exam = booking.slot.examination
    now = datetime.utcnow()
    if booking.status != "Booked" or exam.status != "Booking Open" or (exam.booking_end and now > exam.booking_end):
        flash("This booking can no longer be cancelled.", "warning")
    else:
        booking.status = "Cancelled"
        booking.slot.status = "Available"
        db.session.commit()
        flash("Booking cancelled; it remains in your history.", "success")
    return redirect(url_for("student.dashboard"))


@student_bp.route("/profile", methods=["GET", "POST"])
@role_required("student")
def profile():
    if request.method == "POST":
        try:
            required(request.form, "name", "email")
            email = request.form["email"].strip().lower()
            if not valid_email(email):
                raise ValidationError("Enter a valid email address.")
            duplicate = User.query.filter(User.email == email, User.id != current_user.id).first()
            if duplicate:
                raise ValidationError("That email is already in use.")
            current_user.name, current_user.email = request.form["name"].strip(), email
            current_user.department, current_user.phone = request.form.get("department", "").strip(), request.form.get("phone", "").strip()
            db.session.commit()
            flash("Profile updated.", "success")
        except ValidationError as error:
            report_error(error)
    return render_template("student/profile.html")
