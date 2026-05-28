import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base_class import Base


class TrainerApplication(Base):
    """Represents a prospective trainer's application to join the team."""

    __tablename__ = "trainer_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String, nullable=False, index=True)
    email = Column(String, nullable=False, index=True)
    phone = Column(String, nullable=False)
    alternate_phone = Column(String, nullable=True)
    dob = Column(String, nullable=False)  # ISO Date String: yyyy-mm-dd
    gender = Column(String, nullable=False)
    country = Column(String, nullable=False)
    city = Column(String, nullable=False)
    specialization = Column(Text, nullable=False)
    other_specialization = Column(Text, nullable=True)
    cv_url = Column(String, nullable=False)
    cover_letter_url = Column(String, nullable=True)
    
    # Referees (up to 3)
    referee1_name = Column(String, nullable=True)
    referee1_speciality = Column(String, nullable=True)
    referee1_phone = Column(String, nullable=True)
    referee1_email = Column(String, nullable=True)
    
    referee2_name = Column(String, nullable=True)
    referee2_speciality = Column(String, nullable=True)
    referee2_phone = Column(String, nullable=True)
    referee2_email = Column(String, nullable=True)
    
    referee3_name = Column(String, nullable=True)
    referee3_speciality = Column(String, nullable=True)
    referee3_phone = Column(String, nullable=True)
    referee3_email = Column(String, nullable=True)
    
    status = Column(String, nullable=False, default="pending")  # pending, approved, declined, archived
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
