from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


# --- Custom Numbered Canvas for PDF page counting ---
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#718096"))
        
        # Suppress footer on page 1 if desired, or show on all
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(A4[0] - 54, 36, page_text)
        
        # Draw a thin footer separator line
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 48, A4[0] - 54, 48)
        
        # Add company tag in footer
        self.drawString(54, 36, "Livecode Technologies")
        self.restoreState()


def get_registration_details(registration, course=None):
    """Common utility to parse registration parameters."""
    first_name = registration.first_name
    last_name = registration.last_name
    org = registration.organization or "N/A"
    country = registration.country or "N/A"
    email = registration.email
    
    # Course Title
    course_title = course.title if course else (registration.course_title or "Master Business Analytics and Reporting with Microsoft Excel and Power BI Training Course")
    
    # Location
    location = registration.schedule_location or "N/A"
    if location == "N/A" and course and course.logistics:
        location = course.logistics.location or "Nairobi, Kenya"
    if not location or location == "N/A":
        location = "Nairobi, Kenya"

    # Date
    date_str = registration.schedule_date or "N/A"
    if date_str == "N/A" and course and course.logistics:
        start = course.logistics.start_date or ""
        end = course.logistics.end_date or ""
        if start and end:
            date_str = f"{start} - {end}"
        elif start:
            date_str = start
    if not date_str or date_str == "N/A":
        date_str = datetime.now().strftime("%B %d, %Y")

    # Duration
    duration = "10 days"
    if course and course.logistics and course.logistics.duration:
        duration = course.logistics.duration

    # Price
    price_usd = 2700.0
    price_kes = 0.0
    if course and hasattr(course, 'logistics') and course.logistics:
        price_usd = course.logistics.price_usd if course.logistics.price_usd else 2700.0
        if hasattr(course.logistics, 'price_kes') and course.logistics.price_kes:
            price_kes = course.logistics.price_kes
        else:
            price_kes = price_usd * 135.0  # fallback conversion

    # Pax Count
    pax = 1
    if registration.registration_type == "group" and registration.group_size:
        try:
            pax = int(registration.group_size)
        except ValueError:
            pax = 1

    return {
        "first_name": first_name,
        "last_name": last_name,
        "org": org,
        "country": country,
        "email": email,
        "course_title": course_title,
        "location": location,
        "date_str": date_str,
        "duration": duration,
        "price_usd": price_usd,
        "price_kes": price_kes,
        "pax": pax
    }
