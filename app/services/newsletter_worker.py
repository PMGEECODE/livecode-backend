import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone
from html import escape

from sqlalchemy import select

from app.core.config import settings
from app.core.email import send_email_async
from app.db.models.newsletter import NewsletterDelivery, NewsletterSubscriber
from app.db.models.blog import BlogPost
from app.db.models.course import Course
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def new_unsubscribe_token() -> str:
    return secrets.token_urlsafe(32)


def _unsubscribe_url(token: str) -> str:
    api_base = settings.API_PUBLIC_URL.strip().rstrip("/") if settings.API_PUBLIC_URL else settings.PUBLIC_SITE_URL.strip().rstrip("/")
    return f"{api_base}/api/v1/newsletter/unsubscribe/{token}" if api_base else f"/api/v1/newsletter/unsubscribe/{token}"


def render_newsletter_template(subscriber: NewsletterSubscriber, title_month: str, intro_text: str, blogs: list = None, courses: list = None) -> str:
    name = escape(subscriber.full_name)
    base = settings.PUBLIC_SITE_URL.strip().rstrip("/")
    api_base = settings.API_PUBLIC_URL.strip().rstrip("/") if settings.API_PUBLIC_URL else base
    unsubscribe_url = _unsubscribe_url(subscriber.unsubscribe_token)
    
    blogs_html = ""
    if blogs:
        blogs_html += """
          <!-- Section 1: Livecode Highlights -->
          <tr>
            <td style="padding: 16px 32px; background-color: #ffffff;">
              <h2 style="text-align:center; font-size:13px; font-weight:900; letter-spacing:0.2em; color:#001A4D; margin: 16px 0 24px 0; border-top:1px solid #f1f5f9; border-bottom:1px solid #f1f5f9; padding:12px 0; text-transform:uppercase;">Livecode Highlights</h2>"""
        for blog in blogs:
            content_snippet = (blog.content[:150] + "...") if blog.content else ""
            img_html = ""
            if blog.image_url:
                img_src = f"{api_base}{blog.image_url}" if blog.image_url.startswith("/") else blog.image_url
                img_html = f"""
                <tr>
                  <td style="padding-bottom:12px;">
                    <a href="{base}/blog/{blog.slug}" target="_blank" style="display:block; text-decoration:none;">
                      <img src="{img_src}" alt="{escape(blog.title)}" style="display:block; width:100%; max-width:600px; border-radius:8px; border:1px solid #e2e8f0; object-fit:cover; max-height:200px;" />
                    </a>
                  </td>
                </tr>"""
                
            blogs_html += f"""
              <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom:32px;">
                {img_html}
                <tr>
                  <td>
                    <h3 style="margin:0; font-size:16px; font-weight:800; line-height:1.4;">
                      <a href="{base}/blog/{blog.slug}" target="_blank" style="color:#2563eb; text-decoration:none;">{escape(blog.title)}</a>
                    </h3>
                    <p style="margin:8px 0 12px 0; font-size:13px; color:#475569; line-height:1.6; font-weight:500;">
                      {escape(content_snippet)}
                    </p>
                    <a href="{base}/blog/{blog.slug}" target="_blank" style="font-size:12px; font-weight:700; color:#d97706; text-decoration:none; text-transform:uppercase; letter-spacing:0.05em;">Read the story</a>
                  </td>
                </tr>
              </table>"""
        blogs_html += """
            </td>
          </tr>"""

    courses_html = ""
    if courses:
        courses_html += """
          <!-- Section 2: Upcoming Training Courses -->
          <tr>
            <td style="padding: 16px 32px; background-color: #ffffff;">
              <h2 style="text-align:center; font-size:13px; font-weight:900; letter-spacing:0.2em; color:#001A4D; margin: 16px 0 24px 0; border-top:1px solid #f1f5f9; border-bottom:1px solid #f1f5f9; padding:12px 0; text-transform:uppercase;">Featured Training Programs</h2>"""
        for course in courses:
            desc_snippet = (course.description[:150] + "...") if course.description else ""
            img_html = ""
            if course.image_url:
                img_src = f"{api_base}{course.image_url}" if course.image_url.startswith("/") else course.image_url
                img_html = f"""
                <tr>
                  <td style="padding-bottom:12px;">
                    <a href="{base}/trainings/{course.slug}" target="_blank" style="display:block; text-decoration:none;">
                      <img src="{img_src}" alt="{escape(course.title)}" style="display:block; width:100%; max-width:600px; border-radius:8px; border:1px solid #e2e8f0; object-fit:cover; max-height:200px;" />
                    </a>
                  </td>
                </tr>"""

            courses_html += f"""
              <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom:32px;">
                {img_html}
                <tr>
                  <td>
                    <h3 style="margin:0; font-size:15px; font-weight:800; line-height:1.4;">
                      <a href="{base}/trainings/{course.slug}" target="_blank" style="color:#2563eb; text-decoration:none;">{escape(course.title)}</a>
                    </h3>
                    <p style="margin:8px 0 12px 0; font-size:13px; color:#475569; line-height:1.6; font-weight:500;">
                      {escape(desc_snippet)}
                    </p>
                    <a href="{base}/trainings/{course.slug}" target="_blank" style="font-size:12px; font-weight:700; color:#d97706; text-decoration:none; text-transform:uppercase; letter-spacing:0.05em;">View course syllabus</a>
                  </td>
                </tr>
              </table>"""
        courses_html += """
            </td>
          </tr>"""

    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Livecode Technologies Newsletter</title>
</head>
<body style="margin:0; padding:0; background-color:#f1f5f9; font-family:'Outfit', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; -webkit-font-smoothing:antialiased;">
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f1f5f9; padding:20px 0;">
    <tr>
      <td align="center">
        <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color:#ffffff; border-radius:16px; border:1px solid #e2e8f0; overflow:hidden; box-shadow:0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03);">
          
          <!-- Logo Header -->
          <tr>
            <td align="center" style="padding: 24px 0 16px 0; background-color: #ffffff;">
              <a href="{base}" target="_blank" style="text-decoration:none;">
                <img src="{base}/logo.png" alt="Livecode Technologies" style="display:block; height:48px; max-height:48px; width:auto; border:none; outline:none;" onerror="this.onerror=null; this.src='https://livecodetechnologies.com/logo.png';" />
              </a>
            </td>
          </tr>

          <!-- Purple/Brand-Navy Banner -->
          <tr>
            <td align="center" style="background-color:#001A4D; padding:32px 24px;">
              <table border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td align="center">
                    <span style="display:inline-block; font-size:11px; font-weight:900; letter-spacing:0.25em; color:#F49220; text-transform:uppercase; margin-bottom:8px;">Livecode Technologies</span>
                    <h1 style="margin:0; color:#ffffff; font-size:24px; font-weight:900; letter-spacing:0.05em; text-transform:uppercase;">{title_month} Newsletter</h1>
                    
                    <!-- Category Navigation links -->
                    <table border="0" cellpadding="0" cellspacing="0" style="margin-top:20px;">
                      <tr>
                        <td>
                          <a href="{base}/blog" target="_blank" style="color:#ffffff; font-size:12px; font-weight:700; text-decoration:none; text-transform:uppercase; letter-spacing:0.1em; padding:0 8px;">Blogs & Articles</a>
                        </td>
                        <td style="color:#F49220; font-size:12px; font-weight:700; padding:0 4px;">•</td>
                        <td>
                          <a href="{base}/training-calendar" target="_blank" style="color:#ffffff; font-size:12px; font-weight:700; text-decoration:none; text-transform:uppercase; letter-spacing:0.1em; padding:0 8px;">Training Courses</a>
                        </td>
                        <td style="color:#F49220; font-size:12px; font-weight:700; padding:0 4px;">•</td>
                        <td>
                          <a href="{base}/services" target="_blank" style="color:#ffffff; font-size:12px; font-weight:700; text-decoration:none; text-transform:uppercase; letter-spacing:0.1em; padding:0 8px;">Technical Services</a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Welcome Message -->
          <tr>
            <td style="padding: 32px 32px 16px 32px; background-color: #ffffff;">
              <p style="margin: 0; font-size: 16px; font-weight: 700; color: #001A4D; line-height: 1.4;">Hello {name},</p>
              <p style="margin: 8px 0 0 0; font-size: 14px; font-weight: 500; color: #475569; line-height: 1.6;">{intro_text}</p>
            </td>
          </tr>

          {blogs_html}
          {courses_html}

          <!-- Section 3: Technical Services -->
          <tr>
            <td style="padding: 16px 32px 32px 32px; background-color: #ffffff;">
              <h2 style="text-align:center; font-size:13px; font-weight:900; letter-spacing:0.2em; color:#001A4D; margin: 16px 0 24px 0; border-top:1px solid #f1f5f9; border-bottom:1px solid #f1f5f9; padding:12px 0; text-transform:uppercase;">Technical Support & Management</h2>
              
              <table border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td>
                    <h3 style="margin:0; font-size:15px; font-weight:800; line-height:1.4;">
                      <a href="{base}/services" target="_blank" style="color:#2563eb; text-decoration:none;">24/7 Managed Infrastructure & Cloud Support</a>
                    </h3>
                    <p style="margin:8px 0 16px 0; font-size:13px; color:#475569; line-height:1.6; font-weight:500;">
                      We provide continuous infrastructure monitoring, automated security patches, cloud migrations, database clustering, and high-performance server tuning to ensure that your business-critical assets run smoothly.
                    </p>
                  </td>
                </tr>
              </table>

              <!-- Action Button -->
              <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-top:12px;">
                <tr>
                  <td align="center">
                    <a href="{base}/training-calendar" target="_blank" style="display:inline-block; background-color:#F49220; color:#ffffff; padding:14px 28px; border-radius:8px; text-decoration:none; font-weight:800; font-size:14px; text-transform:uppercase; letter-spacing:0.05em; box-shadow:0 4px 6px -1px rgba(244,146,32,0.2);">Explore Training Calendar</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Notice alert box -->
          <tr>
            <td style="padding: 0 32px; background-color: #ffffff;">
              <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #eff6ff; border: 1px solid #bfdbfe; border-radius: 12px; padding: 16px 20px;">
                <tr>
                  <td>
                    <p style="margin:0; font-size:12px; color:#1e40af; line-height:1.6; font-weight:600; text-align:center;">
                      Ensure that you keep receiving the Livecode newsletter. We automatically send these curated weekly updates to subscribed professional partners. You can manage your preferences or unsubscribe at any time below.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer Banner -->
          <tr>
            <td align="center" style="background-color:#001A4D; padding:40px 24px; margin-top:32px;">
              <table border="0" cellpadding="0" cellspacing="0" width="100%">
                
                <!-- Social Links -->
                <tr>
                  <td align="center" style="padding-bottom:24px;">
                    <a href="https://www.facebook.com/www.livecodetech.co.ke" target="_blank" style="display:inline-block; margin:0 8px; text-decoration:none;">
                      <img src="https://img.icons8.com/ios-filled/50/ffffff/facebook-new.png" alt="Facebook" style="display:block; width:22px; height:22px;" />
                    </a>
                    <a href="https://www.linkedin.com/company/73192786/admin/dashboard/" target="_blank" style="display:inline-block; margin:0 8px; text-decoration:none;">
                      <img src="https://img.icons8.com/ios-filled/50/ffffff/linkedin.png" alt="LinkedIn" style="display:block; width:22px; height:22px;" />
                    </a>
                    <a href="https://x.com/LivecodeL" target="_blank" style="display:inline-block; margin:0 8px; text-decoration:none;">
                      <img src="https://img.icons8.com/ios-filled/50/ffffff/twitter.png" alt="Twitter/X" style="display:block; width:22px; height:22px;" />
                    </a>
                    <a href="{base}" target="_blank" style="display:inline-block; margin:0 8px; text-decoration:none;">
                      <img src="https://img.icons8.com/ios-filled/50/ffffff/domain.png" alt="Website" style="display:block; width:22px; height:22px;" />
                    </a>
                  </td>
                </tr>

                <!-- Address & Legal -->
                <tr>
                  <td align="center" style="color:#94a3b8; font-size:11px; font-weight:500; line-height:1.6; padding-bottom:24px;">
                    <strong>Livecode Technologies Ltd</strong><br />
                    14th Floor, Western Heights, Karuna Road, Nairobi, Kenya<br />
                    <span style="color:#64748b;">© 2026 Livecode Technologies. All rights reserved.</span>
                  </td>
                </tr>

                <!-- Unsubscribe links -->
                <tr>
                  <td align="center">
                    <a href="{base}/contact" target="_blank" style="color:#ffffff; font-size:11px; font-weight:700; text-decoration:none; text-transform:uppercase; letter-spacing:0.05em; padding:0 8px;">Contact Us</a>
                    <span style="color:#F49220; font-size:11px;">|</span>
                    <a href="{base}/privacy-policy" target="_blank" style="color:#ffffff; font-size:11px; font-weight:700; text-decoration:none; text-transform:uppercase; letter-spacing:0.05em; padding:0 8px;">Privacy Policy</a>
                    <span style="color:#F49220; font-size:11px;">|</span>
                    <a href="{unsubscribe_url}" target="_blank" style="color:#F49220; font-size:11px; font-weight:800; text-decoration:underline; text-transform:uppercase; letter-spacing:0.05em; padding:0 8px;">Unsubscribe</a>
                  </td>
                </tr>

              </table>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def welcome_email(subscriber: NewsletterSubscriber, blogs: list = None, courses: list = None) -> tuple[str, str]:
    title_month = datetime.now().strftime("%B %Y").upper()
    intro_text = "Thank you for subscribing to Livecode Technologies. We are thrilled to welcome you to our professional network. As a subscriber, you'll receive weekly updates containing upcoming masterclass training calendars, industry-standard technology blogs, and professional system design insights directly in your inbox."
    
    html_body = render_newsletter_template(subscriber, title_month, intro_text, blogs=blogs, courses=courses)
    return ("Welcome to Livecode Technologies updates", html_body)


def digest_email(subscriber: NewsletterSubscriber, blogs: list = None, courses: list = None) -> tuple[str, str]:
    title_month = datetime.now().strftime("%B %Y").upper()
    intro_text = "We hope you are having an excellent week. Here is your curated weekly digest from Livecode Technologies, featuring our latest technical publications, trending courses, and managed solutions designed to keep you at the absolute forefront of the technology ecosystem."
    
    html_body = render_newsletter_template(subscriber, title_month, intro_text, blogs=blogs, courses=courses)
    return ("Livecode Technologies weekly training update", html_body)


async def queue_delivery(db, subscriber: NewsletterSubscriber, subject: str, html_body: str) -> None:
    db.add(NewsletterDelivery(
        subscriber_email=subscriber.email,
        subject=subject,
        html_body=html_body,
        status="pending",
    ))


async def prepare_newsletter_deliveries() -> None:
    now = datetime.now(timezone.utc)
    digest_cutoff = now - timedelta(days=max(1, settings.NEWSLETTER_DIGEST_INTERVAL_DAYS))

    async with SessionLocal() as db:
        # Fetch dynamic content once for the loop
        blogs_result = await db.execute(select(BlogPost).order_by(BlogPost.published_date.desc()).limit(2))
        blogs = blogs_result.scalars().all()
        
        # We'll use order_by(Course.title) just as a placeholder since func.random() might not be supported universally, 
        # or we can just fetch the latest inserted courses. Let's fetch the first 2.
        courses_result = await db.execute(select(Course).order_by(Course.slug.desc()).limit(2))
        courses = courses_result.scalars().all()

        result = await db.execute(select(NewsletterSubscriber).where(NewsletterSubscriber.is_active == True))  # noqa: E712
        subscribers = result.scalars().all()
        for subscriber in subscribers:
            if not subscriber.welcome_email_sent:
                # 1. Send welcome newsletter to the subscriber
                subject, html_body = welcome_email(subscriber, blogs, courses)
                await queue_delivery(db, subscriber, subject, html_body)
                subscriber.welcome_email_sent = True
                
                # Assume digest isn't needed right after welcome, set the timer
                subscriber.last_digest_sent_at = now
                
                # 2. Send notification ONLY ONCE to the company email target
                company_email_target = (settings.COMPANY_NOTIFICATION_EMAIL or "").strip() or settings.EMAILS_FROM_EMAIL.strip()
                if company_email_target:
                    notification_subject = f"New Newsletter Subscription: {subscriber.full_name}"
                    notification_body = f"""
                    <div style="font-family:sans-serif; padding:20px; background-color:#f8fafc; color:#334155;">
                      <div style="max-width:600px; margin:0 auto; background-color:#ffffff; padding:24px; border:1px solid #e2e8f0; border-radius:12px;">
                        <h2 style="color:#001A4D; margin-top:0;">New Newsletter Registration</h2>
                        <p>A user has successfully registered for the Livecode Technologies weekly newsletter.</p>
                        <hr style="border:none; border-top:1px solid #e2e8f0; margin:16px 0;" />
                        <table cellpadding="4" cellspacing="0" style="font-size:14px; width:100%;">
                          <tr>
                            <td style="font-weight:700; width:120px; color:#475569;">Full Name:</td>
                            <td>{escape(subscriber.full_name)}</td>
                          </tr>
                          <tr>
                            <td style="font-weight:700; color:#475569;">Email Address:</td>
                            <td><a href="mailto:{escape(subscriber.email)}">{escape(subscriber.email)}</a></td>
                          </tr>
                          <tr>
                            <td style="font-weight:700; color:#475569;">Occupation:</td>
                            <td>{escape(subscriber.occupation)}</td>
                          </tr>
                          <tr>
                            <td style="font-weight:700; color:#475569;">Phone Number:</td>
                            <td>{escape(subscriber.phone or 'Not Provided')}</td>
                          </tr>
                          <tr>
                            <td style="font-weight:700; color:#475569;">Source:</td>
                            <td>{escape(subscriber.source or 'Direct / Unknown')}</td>
                          </tr>
                          <tr>
                            <td style="font-weight:700; color:#475569;">Registered At:</td>
                            <td>{subscriber.created_at.strftime('%Y-%m-%d %H:%M:%S') if subscriber.created_at else 'Just now'}</td>
                          </tr>
                        </table>
                      </div>
                    </div>
                    """
                    db.add(NewsletterDelivery(
                        subscriber_email=company_email_target,
                        subject=notification_subject,
                        html_body=notification_body,
                        status="pending",
                    ))
            elif subscriber.last_digest_sent_at is None or subscriber.last_digest_sent_at <= digest_cutoff:
                subject, html_body = digest_email(subscriber, blogs, courses)
                await queue_delivery(db, subscriber, subject, html_body)
                subscriber.last_digest_sent_at = now
        await db.commit()


async def send_pending_deliveries(limit: int = 25) -> None:
    async with SessionLocal() as db:
        result = await db.execute(
            select(NewsletterDelivery)
            .where(NewsletterDelivery.status.in_(["pending", "failed"]))
            .where(NewsletterDelivery.attempts < 3)
            .order_by(NewsletterDelivery.scheduled_at.asc())
            .limit(limit)
        )
        deliveries = result.scalars().all()
        for delivery in deliveries:
            try:
                await send_email_async(delivery.subscriber_email, delivery.subject, delivery.html_body)
                delivery.status = "sent"
                delivery.sent_at = datetime.now(timezone.utc)
                delivery.error_message = None
            except Exception as exc:
                delivery.status = "failed"
                delivery.error_message = str(exc)[:1000]
            finally:
                delivery.attempts = int(delivery.attempts or 0) + 1
        await db.commit()


async def newsletter_worker(stop_event: asyncio.Event) -> None:
    logger.info("Newsletter worker started.")
    while not stop_event.is_set():
        try:
            await prepare_newsletter_deliveries()
            await send_pending_deliveries()
        except Exception as exc:
            logger.error("Newsletter worker cycle failed: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(30, settings.NEWSLETTER_WORKER_INTERVAL_SECONDS))
        except asyncio.TimeoutError:
            pass
    logger.info("Newsletter worker stopped.")

async def trigger_newsletter_worker() -> None:
    """Manually trigger the worker logic for immediate execution (e.g., via BackgroundTasks)."""
    try:
        await prepare_newsletter_deliveries()
        await send_pending_deliveries(limit=50)
    except Exception as exc:
        logger.error("Manual newsletter trigger failed: %s", exc)
