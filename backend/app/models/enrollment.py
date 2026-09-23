import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.core.database import Base
from app.core.enums import EnrollmentStatus
from .base import GUID

class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("course_id", "student_id", name="uq_enrollment_course_student"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[EnrollmentStatus] = mapped_column(Enum(EnrollmentStatus), default=EnrollmentStatus.ENROLLED, nullable=False)
    # 应用层微秒级时间戳，保证候补排序与排队位置计算的确定性
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())

    course = relationship("Course", back_populates="enrollments")
    student = relationship("Student", back_populates="enrollments")
