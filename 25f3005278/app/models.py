"""Database schema: SQLAlchemy ORM models and their relationships."""
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from . import db, login_manager


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class User(UserMixin, db.Model):
    # ORM maps this model to the users table (schema for admin, examiner and student accounts).
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)
    department = db.Column(db.String(100))
    phone = db.Column(db.String(30))
    approved = db.Column(db.Boolean, default=False, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Course(db.Model):
    # ORM schema for courses; each course can have multiple examinations.
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(24), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, default="")
    active = db.Column(db.Boolean, default=True, nullable=False)
    examinations = db.relationship("Examination", back_populates="course", cascade="all, delete-orphan")


class Examination(db.Model):
    # ORM schema for exam configuration and the slot-creation/booking time windows.
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    name = db.Column(db.String(140), nullable=False)
    exam_type = db.Column(db.String(30), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=30)
    max_marks = db.Column(db.Float, nullable=False, default=100)
    slot_start = db.Column(db.DateTime)
    slot_end = db.Column(db.DateTime)
    booking_start = db.Column(db.DateTime)
    booking_end = db.Column(db.DateTime)
    status = db.Column(db.String(30), nullable=False, default="Draft")
    results_published = db.Column(db.Boolean, default=False, nullable=False)
    course = db.relationship("Course", back_populates="examinations")
    rubrics = db.relationship("Rubric", back_populates="examination", cascade="all, delete-orphan")
    slots = db.relationship("ExamSlot", back_populates="examination", cascade="all, delete-orphan")


class Rubric(db.Model):
    # ORM schema for one scored criterion in an examination's evaluation rubric.
    id = db.Column(db.Integer, primary_key=True)
    examination_id = db.Column(db.Integer, db.ForeignKey("examination.id"), nullable=False)
    criterion = db.Column(db.String(120), nullable=False)
    max_marks = db.Column(db.Float, nullable=False)
    weightage = db.Column(db.Float, nullable=False, default=1)
    description = db.Column(db.Text, default="")
    examination = db.relationship("Examination", back_populates="rubrics")


class ExamSlot(db.Model):
    # ORM schema for examiner-created slots; capacity and seats are checked before booking.
    id = db.Column(db.Integer, primary_key=True)
    examination_id = db.Column(db.Integer, db.ForeignKey("examination.id"), nullable=False, index=True)
    examiner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(20), nullable=False, default="Available")
    examination = db.relationship("Examination", back_populates="slots")
    examiner = db.relationship("User", foreign_keys=[examiner_id])
    bookings = db.relationship("Booking", back_populates="slot", cascade="all, delete-orphan")

    @property
    def booked_count(self):
        return sum(b.status != "Cancelled" for b in self.bookings)

    @property
    def seats_left(self):
        return max(0, self.capacity - self.booked_count)


class Booking(db.Model):
    # ORM schema for a student's booking and its persistent cancellation/evaluation history.
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    slot_id = db.Column(db.Integer, db.ForeignKey("exam_slot.id"), nullable=False, index=True)
    booked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Booked")
    marks = db.Column(db.Float)
    remarks = db.Column(db.Text)
    evaluated_at = db.Column(db.DateTime)
    student = db.relationship("User", foreign_keys=[student_id])
    slot = db.relationship("ExamSlot", back_populates="bookings")
    scores = db.relationship("RubricScore", back_populates="booking", cascade="all, delete-orphan")


class RubricScore(db.Model):
    # ORM schema stores per-criterion marks, linked to a booking and rubric row.
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), nullable=False)
    rubric_id = db.Column(db.Integer, db.ForeignKey("rubric.id"), nullable=False)
    marks = db.Column(db.Float, nullable=False)
    booking = db.relationship("Booking", back_populates="scores")
    rubric = db.relationship("Rubric")
