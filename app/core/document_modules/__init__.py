from app.core.document_modules.common import NumberedCanvas, get_registration_details
from app.core.document_modules.invoice import generate_invoice_pdf
from app.core.document_modules.invitation import generate_invitation_letter_pdf
from app.core.document_modules.pre_training import generate_pre_training_form_docx

__all__ = [
    "NumberedCanvas",
    "get_registration_details",
    "generate_invoice_pdf",
    "generate_invitation_letter_pdf",
    "generate_pre_training_form_docx",
]
