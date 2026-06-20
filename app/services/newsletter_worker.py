import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone
from html import escape

from sqlalchemy import select

from app.core.config import settings
from app.core.email import send_email_async
from app.db.models.newsletter import NewsletterDelivery, NewsletterSubscriber, NewsletterTheme
from app.db.models.blog import BlogPost
from app.db.models.course import Course
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def new_unsubscribe_token() -> str:
    return secrets.token_urlsafe(32)


def _unsubscribe_url(token: str) -> str:
    api_base = settings.API_PUBLIC_URL.strip().rstrip("/") if settings.API_PUBLIC_URL else settings.PUBLIC_SITE_URL.strip().rstrip("/")
    return f"{api_base}/api/v1/newsletter/unsubscribe/{token}" if api_base else f"/api/v1/newsletter/unsubscribe/{token}"


DEFAULT_THEME = {
    "primary_color": "#001A4D",
    "secondary_color": "#F49220",
    "bg_color": "#f1f5f9",
    "card_bg": "#ffffff",
    "text_color": "#475569",
    "heading_color": "#001A4D",
    "font_family": "'Outfit', 'Inter', -apple-system, sans-serif"
}


def render_newsletter_template(
    subscriber: NewsletterSubscriber,
    title_month: str,
    intro_text: str,
    blogs: list = None,
    courses: list = None,
    products: list = None,
    services: list = None,
    theme: dict = None
) -> str:
    if not theme:
        theme = DEFAULT_THEME
        
    primary_color = theme.get("primary_color", "#001A4D")
    secondary_color = theme.get("secondary_color", "#F49220")
    bg_color = theme.get("bg_color", "#f1f5f9")
    card_bg = theme.get("card_bg", "#ffffff")
    text_color = theme.get("text_color", "#475569")
    heading_color = theme.get("heading_color", "#001A4D")
    font_family = theme.get("font_family", "'Outfit', 'Inter', -apple-system, sans-serif")
    layout_style = theme.get("template_layout", "classic_card") or "classic_card"

    name = escape(subscriber.full_name)
    base = settings.PUBLIC_SITE_URL.strip().rstrip("/")
    api_base = settings.API_PUBLIC_URL.strip().rstrip("/") if settings.API_PUBLIC_URL else base
    unsubscribe_url = _unsubscribe_url(subscriber.unsubscribe_token)
    
    # Static fallbacks for visual richness
    blogs = list(blogs) if blogs else []
    courses = list(courses) if courses else []
    products = list(products) if products else []
    services = list(services) if services else []

    if not blogs:
        class MockBlog:
            title = "Modern System Design: Achieving Microsecond Latency"
            slug = "system-design-microsecond-latency"
            content = "In this edition of our architecture review, we breakdown the exact strategies used to scale backend messaging pipelines to handle 100k+ concurrent websocket events with sub-millisecond response guarantees."
        blogs = [MockBlog()]
    
    if not courses:
        class MockCourse:
            title = "Enterprise DevOps Masterclass: Kubernetes & GitOps"
            slug = "enterprise-devops-masterclass"
            description = "A comprehensive 5-day bootcamp covering professional container orchestration, CI/CD pipeline hardened security, monitoring stacks, and multi-region failover automation patterns."
        courses = [MockCourse()]

    if not products:
        class MockProduct:
            name = "Livecode Cloud Gateway"
            slug = "livecode-cloud-gateway"
            description = "A secured API gateway and service mesh platform engineered to provide zero-trust communication, rate limiting, and centralized JWT authentication out-of-the-box."
            price = 499.0
            currency = "USD"
            category = "Infrastructure"
        products = [MockProduct()]

    if not services:
        class MockService:
            title = "Cloud & Security Architecture Audit"
            slug = "cloud-security-architecture-audit"
            description = "A complete technical review of your software architecture, database clusters, and cloud settings to detect performance bottlenecks, security vulnerabilities, and cost optimization areas."
        services = [MockService()]

    TECH_IMAGES = [
        "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1531297484001-80022131f5a1?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?w=600&auto=format&fit=crop"
    ]

    def get_item_image(item, default_img_idx: int) -> str:
        url = getattr(item, "image_url", None)
        if url and not url.startswith("/"):
            return url
        elif url:
            return f"{api_base}{url}"
        
        import hashlib
        slug_seed = getattr(item, "slug", getattr(item, "title", getattr(item, "name", str(default_img_idx))))
        h = int(hashlib.md5(slug_seed.encode("utf-8")).hexdigest(), 16)
        return TECH_IMAGES[h % len(TECH_IMAGES)]

    blogs_html = ""
    courses_html = ""
    products_html = ""
    services_html = ""

    if layout_style == "classic_card":
        # Blogs
        if blogs:
            blogs_html += f"""
              <tr>
                <td style="padding: 16px 32px 8px 32px; background-color: {card_bg};">
                  <h2 style="font-size:12px; font-weight:900; letter-spacing:0.15em; color:{heading_color}; margin: 8px 0 20px 0; border-bottom:2px solid {primary_color}20; padding-bottom:8px; text-transform:uppercase;">Latest Technical Publications</h2>"""
            for i, blog in enumerate(blogs):
                content_snippet = (blog.content[:160] + "...") if getattr(blog, "content", None) else ""
                img_src = get_item_image(blog, i)
                blogs_html += f"""
                  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:{card_bg}; border:1px solid #e2e8f0; border-radius:12px; margin-bottom:24px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.02);">
                    <tr>
                      <td>
                        <a href="{base}/blog/{blog.slug}" target="_blank" style="display:block; text-decoration:none;">
                          <img src="{img_src}" alt="{escape(blog.title)}" style="display:block; width:100%; height:180px; object-fit:cover; border-bottom:1px solid #e2e8f0;" />
                        </a>
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:20px;">
                        <span style="display:inline-block; font-size:9px; font-weight:800; color:{secondary_color}; background-color:{secondary_color}12; padding:3px 8px; border-radius:4px; text-transform:uppercase; margin-bottom:10px; letter-spacing:0.05em;">Insight & Architecture</span>
                        <h3 style="margin:0; font-size:16px; font-weight:800; line-height:1.4; color:{heading_color};">
                          <a href="{base}/blog/{blog.slug}" target="_blank" style="color:{heading_color}; text-decoration:none;">{escape(blog.title)}</a>
                        </h3>
                        <p style="margin:8px 0 16px 0; font-size:13px; color:{text_color}; line-height:1.6; font-weight:500;">
                          {escape(content_snippet)}
                        </p>
                        <a href="{base}/blog/{blog.slug}" target="_blank" style="font-size:12px; font-weight:800; color:{secondary_color}; text-decoration:none; text-transform:uppercase; letter-spacing:0.05em;">Read full article &rarr;</a>
                      </td>
                    </tr>
                  </table>"""
            blogs_html += "</td></tr>"

        # Courses
        if courses:
            courses_html += f"""
              <tr>
                <td style="padding: 16px 32px 8px 32px; background-color: {card_bg};">
                  <h2 style="font-size:12px; font-weight:900; letter-spacing:0.15em; color:{heading_color}; margin: 8px 0 20px 0; border-bottom:2px solid {primary_color}20; padding-bottom:8px; text-transform:uppercase;">Masterclass Training Programs</h2>"""
            for i, course in enumerate(courses):
                desc_snippet = (course.description[:160] + "...") if getattr(course, "description", None) else ""
                img_src = get_item_image(course, i + 10)
                courses_html += f"""
                  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:{card_bg}; border:1px solid #e2e8f0; border-radius:12px; margin-bottom:24px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.02);">
                    <tr>
                      <td>
                        <a href="{base}/trainings/{course.slug}" target="_blank" style="display:block; text-decoration:none;">
                          <img src="{img_src}" alt="{escape(course.title)}" style="display:block; width:100%; height:180px; object-fit:cover; border-bottom:1px solid #e2e8f0;" />
                        </a>
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:20px;">
                        <span style="display:inline-block; font-size:9px; font-weight:800; color:#2563eb; background-color:#2563eb12; padding:3px 8px; border-radius:4px; text-transform:uppercase; margin-bottom:10px; letter-spacing:0.05em;">Professional Syllabus</span>
                        <h3 style="margin:0; font-size:16px; font-weight:800; line-height:1.4; color:{heading_color};">
                          <a href="{base}/trainings/{course.slug}" target="_blank" style="color:{heading_color}; text-decoration:none;">{escape(course.title)}</a>
                        </h3>
                        <p style="margin:8px 0 16px 0; font-size:13px; color:{text_color}; line-height:1.6; font-weight:500;">
                          {escape(desc_snippet)}
                        </p>
                        <a href="{base}/trainings/{course.slug}" target="_blank" style="font-size:12px; font-weight:800; color:{secondary_color}; text-decoration:none; text-transform:uppercase; letter-spacing:0.05em;">Explore syllabus & calendar &rarr;</a>
                      </td>
                    </tr>
                  </table>"""
            courses_html += "</td></tr>"

        # Products
        if products:
            products_html += f"""
              <tr>
                <td style="padding: 16px 32px 8px 32px; background-color: {card_bg};">
                  <h2 style="font-size:12px; font-weight:900; letter-spacing:0.15em; color:{heading_color}; margin: 8px 0 20px 0; border-bottom:2px solid {primary_color}20; padding-bottom:8px; text-transform:uppercase;">Software Products & Tools</h2>"""
            for i, prod in enumerate(products):
                desc_snippet = (prod.description[:160] + "...") if getattr(prod, "description", None) else ""
                img_src = get_item_image(prod, i + 20)
                price_str = f"{prod.currency} {prod.price:,.2f}" if getattr(prod, "price", None) is not None else ""
                products_html += f"""
                  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:{card_bg}; border:1px solid #e2e8f0; border-radius:12px; margin-bottom:24px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.02);">
                    <tr>
                      <td>
                        <a href="{base}/products/{prod.slug}" target="_blank" style="display:block; text-decoration:none;">
                          <img src="{img_src}" alt="{escape(prod.name)}" style="display:block; width:100%; height:180px; object-fit:cover; border-bottom:1px solid #e2e8f0;" />
                        </a>
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:20px;">
                        <span style="display:inline-block; font-size:9px; font-weight:800; color:#16a34a; background-color:#16a34a12; padding:3px 8px; border-radius:4px; text-transform:uppercase; margin-bottom:10px; letter-spacing:0.05em;">{escape(prod.category)} • {price_str}</span>
                        <h3 style="margin:0; font-size:16px; font-weight:800; line-height:1.4; color:{heading_color};">
                          <a href="{base}/products/{prod.slug}" target="_blank" style="color:{heading_color}; text-decoration:none;">{escape(prod.name)}</a>
                        </h3>
                        <p style="margin:8px 0 16px 0; font-size:13px; color:{text_color}; line-height:1.6; font-weight:500;">
                          {escape(desc_snippet)}
                        </p>
                        <a href="{base}/products/{prod.slug}" target="_blank" style="font-size:12px; font-weight:800; color:{secondary_color}; text-decoration:none; text-transform:uppercase; letter-spacing:0.05em;">Purchase & Learn More &rarr;</a>
                      </td>
                    </tr>
                  </table>"""
            products_html += "</td></tr>"

        # Services
        if services:
            services_html += f"""
              <tr>
                <td style="padding: 16px 32px 32px 32px; background-color: {card_bg};">
                  <h2 style="font-size:12px; font-weight:900; letter-spacing:0.15em; color:{heading_color}; margin: 8px 0 20px 0; border-bottom:2px solid {primary_color}20; padding-bottom:8px; text-transform:uppercase;">Managed Enterprise Solutions</h2>"""
            for i, srv in enumerate(services):
                desc_snippet = (srv.description[:160] + "...") if getattr(srv, "description", None) else ""
                img_src = get_item_image(srv, i + 30)
                services_html += f"""
                  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:{card_bg}; border:1px solid #e2e8f0; border-radius:12px; margin-bottom:24px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.02);">
                    <tr>
                      <td>
                        <a href="{base}/services" target="_blank" style="display:block; text-decoration:none;">
                          <img src="{img_src}" alt="{escape(srv.title)}" style="display:block; width:100%; height:180px; object-fit:cover; border-bottom:1px solid #e2e8f0;" />
                        </a>
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:20px;">
                        <span style="display:inline-block; font-size:9px; font-weight:800; color:#dc2626; background-color:#dc262612; padding:3px 8px; border-radius:4px; text-transform:uppercase; margin-bottom:10px; letter-spacing:0.05em;">Professional Services</span>
                        <h3 style="margin:0; font-size:16px; font-weight:800; line-height:1.4; color:{heading_color};">
                          <a href="{base}/services" target="_blank" style="color:{heading_color}; text-decoration:none;">{escape(srv.title)}</a>
                        </h3>
                        <p style="margin:8px 0 16px 0; font-size:13px; color:{text_color}; line-height:1.6; font-weight:500;">
                          {escape(desc_snippet)}
                        </p>
                        <a href="{base}/services" target="_blank" style="font-size:12px; font-weight:800; color:{secondary_color}; text-decoration:none; text-transform:uppercase; letter-spacing:0.05em;">Request Consulting Support &rarr;</a>
                      </td>
                    </tr>
                  </table>"""
            services_html += "</td></tr>"

    elif layout_style == "minimalist":
        # Blogs
        if blogs:
            blogs_html += f"""
              <tr>
                <td style="padding: 16px 32px; background-color: {card_bg};">
                  <h2 style="font-size:11px; font-weight:900; letter-spacing:0.2em; color:{heading_color}; margin: 8px 0 16px 0; border-bottom:1px solid {primary_color}15; padding-bottom:6px; text-transform:uppercase;">Insights & Publications</h2>"""
            for blog in blogs:
                content_snippet = (blog.content[:180] + "...") if getattr(blog, "content", None) else ""
                blogs_html += f"""
                  <div style="margin-bottom:24px;">
                    <span style="font-size:9px; font-weight:700; color:{secondary_color}; text-transform:uppercase; letter-spacing:0.05em;">Technical Article</span>
                    <h3 style="margin:4px 0 6px 0; font-size:15px; font-weight:800; line-height:1.3; color:{heading_color};">
                      <a href="{base}/blog/{blog.slug}" target="_blank" style="color:{heading_color}; text-decoration:none;">{escape(blog.title)}</a>
                    </h3>
                    <p style="margin:0 0 10px 0; font-size:13px; color:{text_color}; line-height:1.5;">
                      {escape(content_snippet)}
                    </p>
                    <a href="{base}/blog/{blog.slug}" target="_blank" style="font-size:11px; font-weight:700; color:{primary_color}; text-decoration:none; text-transform:uppercase; letter-spacing:0.05em;">Read Article &rarr;</a>
                  </div>"""
            blogs_html += "</td></tr>"

        # Courses
        if courses:
            courses_html += f"""
              <tr>
                <td style="padding: 16px 32px; background-color: {card_bg};">
                  <h2 style="font-size:11px; font-weight:900; letter-spacing:0.2em; color:{heading_color}; margin: 8px 0 16px 0; border-bottom:1px solid {primary_color}15; padding-bottom:6px; text-transform:uppercase;">Upcoming Training Programs</h2>"""
            for course in courses:
                desc_snippet = (course.description[:180] + "...") if getattr(course, "description", None) else ""
                courses_html += f"""
                  <div style="margin-bottom:24px;">
                    <span style="font-size:9px; font-weight:700; color:#2563eb; text-transform:uppercase; letter-spacing:0.05em;">Professional Syllabus</span>
                    <h3 style="margin:4px 0 6px 0; font-size:15px; font-weight:800; line-height:1.3; color:{heading_color};">
                      <a href="{base}/trainings/{course.slug}" target="_blank" style="color:{heading_color}; text-decoration:none;">{escape(course.title)}</a>
                    </h3>
                    <p style="margin:0 0 10px 0; font-size:13px; color:{text_color}; line-height:1.5;">
                      {escape(desc_snippet)}
                    </p>
                    <a href="{base}/trainings/{course.slug}" target="_blank" style="font-size:11px; font-weight:700; color:{primary_color}; text-decoration:none; text-transform:uppercase; letter-spacing:0.05em;">Explore syllabus &rarr;</a>
                  </div>"""
            courses_html += "</td></tr>"

        # Products
        if products:
            products_html += f"""
              <tr>
                <td style="padding: 16px 32px; background-color: {card_bg};">
                  <h2 style="font-size:11px; font-weight:900; letter-spacing:0.2em; color:{heading_color}; margin: 8px 0 16px 0; border-bottom:1px solid {primary_color}15; padding-bottom:6px; text-transform:uppercase;">Product Catalog</h2>"""
            for prod in products:
                desc_snippet = (prod.description[:180] + "...") if getattr(prod, "description", None) else ""
                price_str = f"{prod.currency} {prod.price:,.2f}" if getattr(prod, "price", None) is not None else ""
                products_html += f"""
                  <div style="margin-bottom:24px;">
                    <span style="font-size:9px; font-weight:700; color:#16a34a; text-transform:uppercase; letter-spacing:0.05em;">{escape(prod.category)} • {price_str}</span>
                    <h3 style="margin:4px 0 6px 0; font-size:15px; font-weight:800; line-height:1.3; color:{heading_color};">
                      <a href="{base}/products/{prod.slug}" target="_blank" style="color:{heading_color}; text-decoration:none;">{escape(prod.name)}</a>
                    </h3>
                    <p style="margin:0 0 10px 0; font-size:13px; color:{text_color}; line-height:1.5;">
                      {escape(desc_snippet)}
                    </p>
                    <a href="{base}/products/{prod.slug}" target="_blank" style="font-size:11px; font-weight:700; color:{primary_color}; text-decoration:none; text-transform:uppercase; letter-spacing:0.05em;">Purchase &rarr;</a>
                  </div>"""
            products_html += "</td></tr>"

        # Services
        if services:
            services_html += f"""
              <tr>
                <td style="padding: 16px 32px; background-color: {card_bg};">
                  <h2 style="font-size:11px; font-weight:900; letter-spacing:0.2em; color:{heading_color}; margin: 8px 0 16px 0; border-bottom:1px solid {primary_color}15; padding-bottom:6px; text-transform:uppercase;">Enterprise Services</h2>"""
            for srv in services:
                desc_snippet = (srv.description[:180] + "...") if getattr(srv, "description", None) else ""
                services_html += f"""
                  <div style="margin-bottom:24px;">
                    <span style="font-size:9px; font-weight:700; color:#dc2626; text-transform:uppercase; letter-spacing:0.05em;">Consulting Support</span>
                    <h3 style="margin:4px 0 6px 0; font-size:15px; font-weight:800; line-height:1.3; color:{heading_color};">
                      <a href="{base}/services" target="_blank" style="color:{heading_color}; text-decoration:none;">{escape(srv.title)}</a>
                    </h3>
                    <p style="margin:0 0 10px 0; font-size:13px; color:{text_color}; line-height:1.5;">
                      {escape(desc_snippet)}
                    </p>
                    <a href="{base}/services" target="_blank" style="font-size:11px; font-weight:700; color:{primary_color}; text-decoration:none; text-transform:uppercase; letter-spacing:0.05em;">Request Consultation &rarr;</a>
                  </div>"""
            services_html += "</td></tr>"

    elif layout_style == "modern_split":
        # Blogs
        if blogs:
            blogs_html += f"""
              <tr>
                <td style="padding: 16px 32px 8px 32px; background-color: {card_bg};">
                  <h2 style="font-size:12px; font-weight:900; letter-spacing:0.15em; color:{heading_color}; margin: 8px 0 20px 0; border-bottom:2px solid {primary_color}20; padding-bottom:8px; text-transform:uppercase;">Technical Publications</h2>"""
            for i, blog in enumerate(blogs):
                content_snippet = (blog.content[:130] + "...") if getattr(blog, "content", None) else ""
                img_src = get_item_image(blog, i)
                is_even = i % 2 == 0
                image_td = f'<td width="160" valign="top" style="padding-right:16px;"><a href="{base}/blog/{blog.slug}" target="_blank"><img src="{img_src}" alt="" style="display:block; width:160px; height:120px; object-fit:cover; border-radius:8px;" /></a></td>'
                text_td = f"""<td valign="top">
                  <span style="font-size:9px; font-weight:800; color:{secondary_color}; text-transform:uppercase; letter-spacing:0.05em;">Insight</span>
                  <h3 style="margin:2px 0 6px 0; font-size:15px; font-weight:800; line-height:1.3; color:{heading_color};">
                    <a href="{base}/blog/{blog.slug}" target="_blank" style="color:{heading_color}; text-decoration:none;">{escape(blog.title)}</a>
                  </h3>
                  <p style="margin:0 0 8px 0; font-size:12px; color:{text_color}; line-height:1.5;">{escape(content_snippet)}</p>
                  <a href="{base}/blog/{blog.slug}" target="_blank" style="font-size:11px; font-weight:800; color:{secondary_color}; text-decoration:none; text-transform:uppercase;">Read Article &rarr;</a>
                </td>"""
                cells = f"{image_td}{text_td}" if is_even else f"{text_td}<td width=\"160\" valign=\"top\" style=\"padding-left:16px;\"><a href=\"{base}/blog/{blog.slug}\" target=\"_blank\"><img src=\"{img_src}\" alt=\"\" style=\"display:block; width:160px; height:120px; object-fit:cover; border-radius:8px;\" /></a></td>"
                blogs_html += f"""
                  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom:24px; background-color:{card_bg};">
                    <tr>{cells}</tr>
                  </table>"""
            blogs_html += "</td></tr>"

        # Courses
        if courses:
            courses_html += f"""
              <tr>
                <td style="padding: 16px 32px 8px 32px; background-color: {card_bg};">
                  <h2 style="font-size:12px; font-weight:900; letter-spacing:0.15em; color:{heading_color}; margin: 8px 0 20px 0; border-bottom:2px solid {primary_color}20; padding-bottom:8px; text-transform:uppercase;">Training Masterclasses</h2>"""
            for i, course in enumerate(courses):
                desc_snippet = (course.description[:130] + "...") if getattr(course, "description", None) else ""
                img_src = get_item_image(course, i + 10)
                is_even = i % 2 == 1
                image_td = f'<td width="160" valign="top" style="padding-right:16px;"><a href="{base}/trainings/{course.slug}" target="_blank"><img src="{img_src}" alt="" style="display:block; width:160px; height:120px; object-fit:cover; border-radius:8px;" /></a></td>'
                text_td = f"""<td valign="top">
                  <span style="font-size:9px; font-weight:800; color:#2563eb; text-transform:uppercase; letter-spacing:0.05em;">Masterclass</span>
                  <h3 style="margin:2px 0 6px 0; font-size:15px; font-weight:800; line-height:1.3; color:{heading_color};">
                    <a href="{base}/trainings/{course.slug}" target="_blank" style="color:{heading_color}; text-decoration:none;">{escape(course.title)}</a>
                  </h3>
                  <p style="margin:0 0 8px 0; font-size:12px; color:{text_color}; line-height:1.5;">{escape(desc_snippet)}</p>
                  <a href="{base}/trainings/{course.slug}" target="_blank" style="font-size:11px; font-weight:800; color:{secondary_color}; text-decoration:none; text-transform:uppercase;">Explore Syllabus &rarr;</a>
                </td>"""
                cells = f"{image_td}{text_td}" if is_even else f"{text_td}<td width=\"160\" valign=\"top\" style=\"padding-left:16px;\"><a href=\"{base}/trainings/{course.slug}\" target=\"_blank\"><img src=\"{img_src}\" alt=\"\" style=\"display:block; width:160px; height:120px; object-fit:cover; border-radius:8px;\" /></a></td>"
                courses_html += f"""
                  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom:24px; background-color:{card_bg};">
                    <tr>{cells}</tr>
                  </table>"""
            courses_html += "</td></tr>"

        # Products
        if products:
            products_html += f"""
              <tr>
                <td style="padding: 16px 32px 8px 32px; background-color: {card_bg};">
                  <h2 style="font-size:12px; font-weight:900; letter-spacing:0.15em; color:{heading_color}; margin: 8px 0 20px 0; border-bottom:2px solid {primary_color}20; padding-bottom:8px; text-transform:uppercase;">Software Products</h2>"""
            for i, prod in enumerate(products):
                desc_snippet = (prod.description[:130] + "...") if getattr(prod, "description", None) else ""
                img_src = get_item_image(prod, i + 20)
                price_str = f"{prod.currency} {prod.price:,.2f}" if getattr(prod, "price", None) is not None else ""
                is_even = i % 2 == 0
                image_td = f'<td width="160" valign="top" style="padding-right:16px;"><a href="{base}/products/{prod.slug}" target="_blank"><img src="{img_src}" alt="" style="display:block; width:160px; height:120px; object-fit:cover; border-radius:8px;" /></a></td>'
                text_td = f"""<td valign="top">
                  <span style="font-size:9px; font-weight:800; color:#16a34a; text-transform:uppercase; letter-spacing:0.05em;">{escape(prod.category)} • {price_str}</span>
                  <h3 style="margin:2px 0 6px 0; font-size:15px; font-weight:800; line-height:1.3; color:{heading_color};">
                    <a href="{base}/products/{prod.slug}" target="_blank" style="color:{heading_color}; text-decoration:none;">{escape(prod.name)}</a>
                  </h3>
                  <p style="margin:0 0 8px 0; font-size:12px; color:{text_color}; line-height:1.5;">{escape(desc_snippet)}</p>
                  <a href="{base}/products/{prod.slug}" target="_blank" style="font-size:11px; font-weight:800; color:{secondary_color}; text-decoration:none; text-transform:uppercase;">Get Details &rarr;</a>
                </td>"""
                cells = f"{image_td}{text_td}" if is_even else f"{text_td}<td width=\"160\" valign=\"top\" style=\"padding-left:16px;\"><a href=\"{base}/products/{prod.slug}\" target=\"_blank\"><img src=\"{img_src}\" alt=\"\" style=\"display:block; width:160px; height:120px; object-fit:cover; border-radius:8px;\" /></a></td>"
                products_html += f"""
                  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom:24px; background-color:{card_bg};">
                    <tr>{cells}</tr>
                  </table>"""
            products_html += "</td></tr>"

        # Services
        if services:
            services_html += f"""
              <tr>
                <td style="padding: 16px 32px 32px 32px; background-color: {card_bg};">
                  <h2 style="font-size:12px; font-weight:900; letter-spacing:0.15em; color:{heading_color}; margin: 8px 0 20px 0; border-bottom:2px solid {primary_color}20; padding-bottom:8px; text-transform:uppercase;">Enterprise Support</h2>"""
            for i, srv in enumerate(services):
                desc_snippet = (srv.description[:130] + "...") if getattr(srv, "description", None) else ""
                img_src = get_item_image(srv, i + 30)
                is_even = i % 2 == 1
                image_td = f'<td width="160" valign="top" style="padding-right:16px;"><a href="{base}/services" target="_blank"><img src="{img_src}" alt="" style="display:block; width:160px; height:120px; object-fit:cover; border-radius:8px;" /></a></td>'
                text_td = f"""<td valign="top">
                  <span style="font-size:9px; font-weight:800; color:#dc2626; text-transform:uppercase; letter-spacing:0.05em;">Services</span>
                  <h3 style="margin:2px 0 6px 0; font-size:15px; font-weight:800; line-height:1.3; color:{heading_color};">
                    <a href="{base}/services" target="_blank" style="color:{heading_color}; text-decoration:none;">{escape(srv.title)}</a>
                  </h3>
                  <p style="margin:0 0 8px 0; font-size:12px; color:{text_color}; line-height:1.5;">{escape(desc_snippet)}</p>
                  <a href="{base}/services" target="_blank" style="font-size:11px; font-weight:800; color:{secondary_color}; text-decoration:none; text-transform:uppercase;">Request Info &rarr;</a>
                </td>"""
                cells = f"{image_td}{text_td}" if is_even else f"{text_td}<td width=\"160\" valign=\"top\" style=\"padding-left:16px;\"><a href=\"{base}/services\" target=\"_blank\"><img src=\"{img_src}\" alt=\"\" style=\"display:block; width:160px; height:120px; object-fit:cover; border-radius:8px;\" /></a></td>"
                services_html += f"""
                  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom:24px; background-color:{card_bg};">
                    <tr>{cells}</tr>
                  </table>"""
            services_html += "</td></tr>"

    elif layout_style == "compact_digest":
        blogs_html += f"""
          <tr>
            <td style="padding: 16px 32px 32px 32px; background-color: {card_bg};">
              <h2 style="font-size:12px; font-weight:900; letter-spacing:0.15em; color:{heading_color}; margin: 8px 0 20px 0; border-bottom:2px solid {primary_color}20; padding-bottom:8px; text-transform:uppercase;">Weekly News & Updates Digest</h2>
              <table border="0" cellpadding="0" cellspacing="0" width="100%">"""
              
        all_items = []
        for b in blogs:
            all_items.append(("Insight", b.title, f"{base}/blog/{b.slug}", getattr(b, "content", "")[:120] + "...", secondary_color))
        for c in courses:
            all_items.append(("Course", c.title, f"{base}/trainings/{c.slug}", getattr(c, "description", "")[:120] + "...", "#2563eb"))
        for p in products:
            all_items.append(("Product", p.name, f"{base}/products/{p.slug}", getattr(p, "description", "")[:120] + "...", "#16a34a"))
        for s in services:
            all_items.append(("Service", s.title, f"{base}/services", getattr(s, "description", "")[:120] + "...", "#dc2626"))
            
        for badge, title, link, snippet, badge_color in all_items:
            blogs_html += f"""
              <tr style="border-bottom:1px solid #f1f5f9;">
                <td style="padding:12px 0; border-bottom:1px solid #f1f5f9;">
                  <span style="display:inline-block; font-size:8px; font-weight:900; color:{badge_color}; background-color:{badge_color}10; padding:2px 6px; border-radius:3px; text-transform:uppercase; margin-right:8px; vertical-align:middle; letter-spacing:0.05em;">{badge}</span>
                  <strong style="font-size:14px; color:{heading_color}; vertical-align:middle;">
                    <a href="{link}" target="_blank" style="color:{heading_color}; text-decoration:none;">{escape(title)}</a>
                  </strong>
                  <p style="margin:4px 0 0 0; font-size:12px; color:{text_color}; line-height:1.4;">{escape(snippet)}</p>
                </td>
              </tr>"""
              
        blogs_html += """
              </table>
            </td>
          </tr>"""

    header_block = f"""
          <!-- Logo Header -->
          <tr>
            <td align="center" style="padding: 24px 0 16px 0; background-color: {card_bg};">
              <a href="{base}" target="_blank" style="text-decoration:none;">
                <img src="{base}/logo.png" alt="Livecode Technologies" style="display:block; height:48px; max-height:48px; width:auto; border:none; outline:none;" onerror="this.onerror=null; this.src='https://livecodetechnologies.com/logo.png';" />
              </a>
            </td>
          </tr>

          <!-- Purple/Brand-Navy Banner -->
          <tr>
            <td align="center" style="background-color:{primary_color}; padding:32px 24px;">
              <table border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td align="center">
                    <span style="display:inline-block; font-size:11px; font-weight:900; letter-spacing:0.25em; color:{secondary_color}; text-transform:uppercase; margin-bottom:8px;">Livecode Technologies</span>
                    <h1 style="margin:0; color:#ffffff; font-size:24px; font-weight:900; letter-spacing:0.05em; text-transform:uppercase;">{title_month} Newsletter</h1>
                    
                    <!-- Category Navigation links -->
                    <table border="0" cellpadding="0" cellspacing="0" style="margin-top:20px;">
                      <tr>
                        <td>
                          <a href="{base}/blog" target="_blank" style="color:#ffffff; font-size:12px; font-weight:700; text-decoration:none; text-transform:uppercase; letter-spacing:0.1em; padding:0 8px;">Blogs & Articles</a>
                        </td>
                        <td style="color:{secondary_color}; font-size:12px; font-weight:700; padding:0 4px;">•</td>
                        <td>
                          <a href="{base}/training-calendar" target="_blank" style="color:#ffffff; font-size:12px; font-weight:700; text-decoration:none; text-transform:uppercase; letter-spacing:0.1em; padding:0 8px;">Training Courses</a>
                        </td>
                        <td style="color:{secondary_color}; font-size:12px; font-weight:700; padding:0 4px;">•</td>
                        <td>
                          <a href="{base}/services" target="_blank" style="color:#ffffff; font-size:12px; font-weight:700; text-decoration:none; text-transform:uppercase; letter-spacing:0.1em; padding:0 8px;">Technical Services</a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""

    if layout_style == "minimalist":
        header_block = f"""
          <!-- Minimalist Logo Header -->
          <tr>
            <td align="center" style="padding: 32px 0; background-color: {card_bg}; border-bottom:1px solid #e2e8f0;">
              <a href="{base}" target="_blank" style="text-decoration:none; display:inline-block; margin-bottom:16px;">
                <img src="{base}/logo.png" alt="Livecode Technologies" style="display:block; height:40px; max-height:40px; width:auto; border:none; outline:none;" onerror="this.onerror=null; this.src='https://livecodetechnologies.com/logo.png';" />
              </a>
              <div style="font-size:10px; font-weight:900; letter-spacing:0.3em; color:{primary_color}; text-transform:uppercase; margin-bottom:4px;">Livecode Technologies</div>
              <h1 style="margin:0; color:{heading_color}; font-size:20px; font-weight:800; letter-spacing:0.05em; text-transform:uppercase;">{title_month} Digest</h1>
            </td>
          </tr>"""

    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Livecode Technologies Newsletter</title>
</head>
<body style="margin:0; padding:0; background-color:{bg_color}; font-family:{font_family}; -webkit-font-smoothing:antialiased;">
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:{bg_color}; padding:32px 0;">
    <tr>
      <td align="center">
        <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color:{card_bg}; border-radius:16px; border:1px solid #e2e8f0; overflow:hidden; box-shadow:0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03);">
          
          {header_block}

          <!-- Welcome Message -->
          <tr>
            <td style="padding: 32px 32px 16px 32px; background-color: {card_bg};">
              <p style="margin: 0; font-size: 16px; font-weight: 700; color: {heading_color}; line-height: 1.4;">Hello {name},</p>
              <p style="margin: 8px 0 0 0; font-size: 14px; font-weight: 500; color: {text_color}; line-height: 1.6;">{intro_text}</p>
            </td>
          </tr>

          {blogs_html}
          {courses_html}
          {products_html}
          {services_html}

          <!-- Notice alert box -->
          <tr>
            <td style="padding: 0 32px; background-color: {card_bg};">
              <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: {bg_color}; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px 20px;">
                <tr>
                  <td>
                    <p style="margin:0; font-size:12px; color:{heading_color}; line-height:1.6; font-weight:600; text-align:center;">
                      Ensure that you keep receiving the Livecode newsletter. We automatically send these curated weekly updates to subscribed professional partners. You can manage your preferences or unsubscribe at any time below.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer Banner -->
          <tr>
            <td align="center" style="background-color:{primary_color}; padding:40px 24px; margin-top:32px;">
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
                    <span style="color:{secondary_color}; font-size:11px;">|</span>
                    <a href="{base}/privacy-policy" target="_blank" style="color:#ffffff; font-size:11px; font-weight:700; text-decoration:none; text-transform:uppercase; letter-spacing:0.05em; padding:0 8px;">Privacy Policy</a>
                    <span style="color:{secondary_color}; font-size:11px;">|</span>
                    <a href="{unsubscribe_url}" target="_blank" style="color:{secondary_color}; font-size:11px; font-weight:800; text-decoration:underline; text-transform:uppercase; letter-spacing:0.05em; padding:0 8px;">Unsubscribe</a>
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


def welcome_email(subscriber: NewsletterSubscriber, blogs: list = None, courses: list = None, products: list = None, services: list = None, theme: dict = None) -> tuple[str, str]:
    title_month = datetime.now().strftime("%B %Y").upper()
    intro_text = "Thank you for subscribing to Livecode Technologies. We are thrilled to welcome you to our professional network. As a subscriber, you'll receive weekly updates containing upcoming masterclass training calendars, industry-standard technology blogs, and professional system design insights directly in your inbox."
    
    html_body = render_newsletter_template(subscriber, title_month, intro_text, blogs=blogs, courses=courses, products=products, services=services, theme=theme)
    return ("Welcome to Livecode Technologies updates", html_body)


def digest_email(subscriber: NewsletterSubscriber, blogs: list = None, courses: list = None, products: list = None, services: list = None, theme: dict = None) -> tuple[str, str]:
    title_month = datetime.now().strftime("%B %Y").upper()
    intro_text = "We hope you are having an excellent week. Here is your curated weekly digest from Livecode Technologies, featuring our latest technical publications, trending courses, and managed solutions designed to keep you at the absolute forefront of the technology ecosystem."
    
    html_body = render_newsletter_template(subscriber, title_month, intro_text, blogs=blogs, courses=courses, products=products, services=services, theme=theme)
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
        # Fetch active theme if any
        theme_dict = None
        try:
            theme_result = await db.execute(select(NewsletterTheme).where(NewsletterTheme.is_active == True))
            active_theme = theme_result.scalars().first()
            if active_theme:
                theme_dict = {
                    "primary_color": active_theme.primary_color,
                    "secondary_color": active_theme.secondary_color,
                    "bg_color": active_theme.bg_color,
                    "card_bg": active_theme.card_bg,
                    "text_color": active_theme.text_color,
                    "heading_color": active_theme.heading_color,
                    "font_family": active_theme.font_family,
                    "template_layout": active_theme.template_layout,
                }
        except Exception as e:
            logger.warning("Could not fetch active newsletter theme: %s. Using default theme.", e)

        # Fetch dynamic content once for the loop
        from app.db.models.product import Product
        from app.db.models.service import Service

        blogs_result = await db.execute(select(BlogPost).order_by(BlogPost.published_date.desc()).limit(2))
        blogs = blogs_result.scalars().all()
        
        courses_result = await db.execute(select(Course).order_by(Course.slug.desc()).limit(2))
        courses = courses_result.scalars().all()

        products_result = await db.execute(select(Product).where(Product.is_active == True).limit(2))
        products = products_result.scalars().all()

        services_result = await db.execute(select(Service).limit(2))
        services = services_result.scalars().all()

        result = await db.execute(select(NewsletterSubscriber).where(NewsletterSubscriber.is_active == True))  # noqa: E712
        subscribers = result.scalars().all()
        for subscriber in subscribers:
            if not subscriber.welcome_email_sent:
                # 1. Send welcome newsletter to the subscriber
                subject, html_body = welcome_email(subscriber, blogs, courses, products, services, theme=theme_dict)
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
                subject, html_body = digest_email(subscriber, blogs, courses, products, services, theme=theme_dict)
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
