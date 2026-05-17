import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from app.db.base_class import Base


class CourseRegistration(Base):
    """Stores individual course registration submissions."""
    __tablename__ = "course_registration"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Course context
    course_id = Column(UUID(as_uuid=True), ForeignKey("course.id", ondelete="SET NULL"), nullable=True, index=True)
    course_title = Column(String, nullable=False)
    schedule_date = Column(String, nullable=True)
    schedule_location = Column(String, nullable=True)
    registration_type = Column(String, nullable=False, default="individual")  # individual | group

    # Personal details
    title = Column(String, nullable=True)
    first_name = Column(String, nullable=False)
    middle_name = Column(String, nullable=True)
    last_name = Column(String, nullable=False)
    gender = Column(String, nullable=True)
    organization = Column(String, nullable=True)
    department = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=False, index=True)
    official_email = Column(String, nullable=True)
    country = Column(String, nullable=True)
    city = Column(String, nullable=True)
    address = Column(String, nullable=True)

    # Additional info
    how_heard = Column(String, nullable=True)
    accommodation = Column(Boolean, nullable=True)
    airport_pickup = Column(Boolean, nullable=True)
    additional_info = Column(Text, nullable=True)

    # Group registration
    group_size = Column(String, nullable=True)
    group_members_json = Column(Text, nullable=True)  # JSON string for group members

    # Status
    status = Column(String, nullable=False, default="pending")  # pending | confirmed | cancelled

    def __init__(
        self,
        *,
        course_id = None,
        course_title = None,
        schedule_date = None,
        schedule_location = None,
        registration_type = "individual",
        title = None,
        first_name = None,
        middle_name = None,
        last_name = None,
        gender = None,
        organization = None,
        department = None,
        phone = None,
        email = None,
        official_email = None,
        country = None,
        city = None,
        address = None,
        how_heard = None,
        accommodation = None,
        airport_pickup = None,
        additional_info = None,
        group_size = None,
        group_members_json = None,
        status = "pending",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.course_id = course_id
        self.course_title = course_title
        self.schedule_date = schedule_date
        self.schedule_location = schedule_location
        self.registration_type = registration_type
        self.title = title
        self.first_name = first_name
        self.middle_name = middle_name
        self.last_name = last_name
        self.gender = gender
        self.organization = organization
        self.department = department
        self.phone = phone
        self.email = email
        self.official_email = official_email
        self.country = country
        self.city = city
        self.address = address
        self.how_heard = how_heard
        self.accommodation = accommodation
        self.airport_pickup = airport_pickup
        self.additional_info = additional_info
        self.group_size = group_size
        self.group_members_json = group_members_json
        self.status = status
