import asyncio
import json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import delete
from app.db.models.course import Course
from app.db.models.schedule import Schedule
from app.core.config import settings

# Content Mapping
TITLE = "Content Management System Using PHP and MYSQL Course"
SLUG = "php-mysql-cms-course"
CATEGORY = "Web Design & Development"
DURATION = "10 Days"
LOCATION = "Nairobi, Kenya"
PRICE_KES = 138000.0
PRICE_USD = 2000.0

CURRICULUM = [
    {
        "id": "meta-1",
        "type": "metadata",
        "title": TITLE,
        "slug": SLUG,
        "category": CATEGORY,
        "image_url": "https://images.unsplash.com/photo-1599507593499-a3f7f7d9a2cc?auto=format&fit=crop&q=80&w=1200"
    },
    {
        "id": "log-1",
        "type": "logistics",
        "duration": DURATION,
        "location": LOCATION,
        "start_date": "2026-05-18",
        "end_date": "2026-05-29",
        "price_kes": str(int(PRICE_KES)),
        "price_usd": str(int(PRICE_USD))
    },
    {
        "id": "sh-1",
        "type": "section_header",
        "title": "Course Overview",
        "icon": "Info"
    },
    {
        "id": "sub-1",
        "type": "subheading",
        "text": "INTRODUCTION"
    },
    {
        "id": "p-1",
        "type": "paragraph",
        "content": "PHP is an award-winning content management system (CMS), which enables you to easily build many types of website. This PHP course will allow users to create a dynamic interactive website from scratch using the free PHP Content Management System (CMS). Each participant will learn how to create a professional website using the PHP Content Management System. PHP is open source and free for all."
    },
    {
        "id": "sub-2",
        "type": "subheading",
        "text": "WHO IS THIS TRAINING INTENDED FOR?"
    },
    {
        "id": "p-2",
        "type": "paragraph",
        "content": "The PHP course is a must for web designers and web developers. It will be an important foundation for anyone maintaining or creating websites. Journalist, post high school students, university and college students, early career professionals, supervisors and team leaders and senior executives or person’s interest to understand how professional websites are authored may also attend."
    },
    {
        "id": "sh-2",
        "type": "section_header",
        "title": "Learning Objectives",
        "icon": "Target"
    },
    {
        "id": "l-1",
        "type": "list",
        "listStyle": "check",
        "items": [
            "All fundamentals of HTML, CSS and Javascript",
            "All PHP Fundamentals and Building Blocks with practical implementation in Projects",
            "Form Validation with most Secure way using Regular Expressions",
            "Making web pages dynamic with the variety of PHP Techniques",
            "Employee Management System CRUD Application in PHP",
            "Complete CMS (Content Management System) with Admin-Panel",
            "Getting Started with Bootstrap Framework",
            "Using PHP Sessions and pass information easily on different modules of Project",
            "Stunning Blog with Commenting functionality",
            "Sending Email using PHP"
        ]
    },
    {
        "id": "sh-3",
        "type": "section_header",
        "title": "Training Content",
        "icon": "BookOpen"
    },
    {
        "id": "sub-3",
        "type": "subheading",
        "text": "Module One: HTML and CSS Basics"
    },
    {
        "id": "l-2",
        "type": "list",
        "listStyle": "disc",
        "items": [
            "What is it HTML and how we use it",
            "Versions of HTML",
            "Creating a Basic Web Page",
            "Insert content",
            "Create a Basic Page Structure",
            "Basic HTML Formatting",
            "Inserting images",
            "Create hypertext Links",
            "What is CSS and how we use it",
            "Creating CSS styles",
            "Basic formatting with CSS",
            "Managing CSS styles",
            "Formatting links with CSS"
        ]
    },
    {
        "id": "sub-4",
        "type": "subheading",
        "text": "Module Two: JavaScript Basics"
    },
    {
        "id": "l-3",
        "type": "list",
        "listStyle": "disc",
        "items": [
            "What is JavaScript and how we use it",
            "Benefits of JavaScript",
            "Interactivity in HTML",
            "Implement basic effects for your content",
            "The future of Web development"
        ]
    },
    {
        "id": "sub-5",
        "type": "subheading",
        "text": "Module Three: Building Blocks of PHP"
    },
    {
        "id": "l-4",
        "type": "list",
        "listStyle": "disc",
        "items": [
            "Requirements overview",
            "XAMP Downloading and Installing",
            "XAMP Server",
            "XAMP Files and Solving Error",
            "Variable, Constants, Strings, Numbers",
            "Arrays & Arrays Functions",
            "If Statements, Operators",
            "Loops (For, While, For-each)",
            "Switch Statements, Branching",
            "User Defined Functions, Re-usability",
            "Static, Local, Global & Super Global Variables"
        ]
    },
    {
        "id": "sub-6",
        "type": "subheading",
        "text": "Module Seven: Employee Management"
    },
    {
        "id": "l-5",
        "type": "list",
        "listStyle": "disc",
        "items": [
            "Working with Database and codes",
            "Creating DB and Table",
            "Establishing Connection",
            "Form Creation and Applying Styles",
            "PHP and Query Creation",
            "View, Delete, Update, Search From Database",
            "SQL Injection & Styling"
        ]
    },
    {
        "id": "sh-4",
        "type": "section_header",
        "title": "General Notes",
        "icon": "Award"
    },
    {
        "id": "sub-7",
        "type": "subheading",
        "text": "Methodology"
    },
    {
        "id": "p-3",
        "type": "paragraph",
        "content": "This instructor led training course is delivered using a blended learning approach and comprises of presentations, guided sessions of practical exercise, web based tutorials and group work. Our facilitators are seasoned industry experts with years of experience, working as professional and trainers in these fields."
    },
    {
        "id": "sub-8",
        "type": "subheading",
        "text": "Accreditation"
    },
    {
        "id": "p-4",
        "type": "paragraph",
        "content": "Upon successful completion of this training, participants will be issued with a certificate of participation."
    },
    {
        "id": "sub-9",
        "type": "subheading",
        "text": "Training Fees"
    },
    {
        "id": "p-5",
        "type": "paragraph",
        "content": "The course fees is KES 138,000.00 or USD 2,000.00 exclusive of VAT. The course fees covers the course tuition, training materials, two (2) break refreshments, lunch and study visits. Participants will cater for their travel and accommodation costs."
    },
    {
        "id": "sh-5",
        "type": "section_header",
        "title": "Schedules",
        "icon": "CalendarDays"
    },
    {
        "id": "sched-1",
        "type": "schedules",
        "schedules": [
            {
                "date_range": "18 May – 29 May",
                "location": "Nairobi, Kenya",
                "mode": "physical",
                "price_kes": "138000",
                "price_usd": "2000",
                "year": "2026"
            }
        ]
    }
]

async def clear_and_seed():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as session:
        # Clear all
        await session.execute(delete(Schedule))
        await session.execute(delete(Course))
        
        # Create new course
        course_data = {
            "title": TITLE,
            "slug": SLUG,
            "category": CATEGORY,
            "duration": DURATION,
            "location": LOCATION,
            "price_kes": PRICE_KES,
            "price_usd": PRICE_USD,
            "curriculum": json.dumps(CURRICULUM),
            "image_url": "https://images.unsplash.com/photo-1599507593499-a3f7f7d9a2cc?auto=format&fit=crop&q=80&w=1200"
        }
        course = Course(**course_data)
        session.add(course)
        await session.flush() # Get course ID
        
        # Add schedules to Schedule table as well for the sidebar to work
        schedule_data = {
            "course_id": course.id,
            "date_range": "18 May – 29 May",
            "location": "Nairobi, Kenya",
            "mode": "physical",
            "price_kes": PRICE_KES,
            "price_usd": PRICE_USD,
            "year": 2026
        }
        schedule = Schedule(**schedule_data)
        session.add(schedule)
        
        await session.commit()
        print(f"Database cleared. Course '{TITLE}' created successfully!")

if __name__ == "__main__":
    asyncio.run(clear_and_seed())
