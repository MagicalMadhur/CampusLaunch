"""
PDF Resume Generator — Creates professional PDF resumes using fpdf2.
"""

from fpdf import FPDF
import os
import tempfile


class ResumePDF(FPDF):
    """Custom PDF class for resume generation."""

    DARK_BLUE = (26, 58, 95)
    MEDIUM_BLUE = (41, 98, 155)
    LIGHT_GRAY = (100, 100, 100)
    BLACK = (30, 30, 30)
    WHITE = (255, 255, 255)
    ACCENT = (41, 128, 185)
    LINE_COLOR = (200, 200, 200)

    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)

    def _section_title(self, title):
        """Render a section heading with a line underneath."""
        self.ln(4)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*self.DARK_BLUE)
        self.cell(0, 8, title.upper(), new_x="LMARGIN", new_y="NEXT")
        # Draw accent line
        self.set_draw_color(*self.ACCENT)
        self.set_line_width(0.6)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)

    def _body_text(self, text, bold=False):
        style = "B" if bold else ""
        self.set_font("Helvetica", style, 10)
        self.set_text_color(*self.BLACK)
        self.multi_cell(0, 5, text)

    def _label_value(self, label, value):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*self.LIGHT_GRAY)
        self.cell(30, 5, label + ":")
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*self.BLACK)
        self.cell(0, 5, value, new_x="LMARGIN", new_y="NEXT")

    def _date_range(self, start, end):
        if start or end:
            return f"{start or '?'} — {end or 'Present'}"
        return ""

    def _bullet(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*self.BLACK)
        x = self.get_x()
        self.cell(5, 5, chr(8226))  # bullet char
        self.multi_cell(0, 5, text)


def generate_resume_pdf(data):
    """
    Generate a professional PDF resume from structured data dict.

    data keys:
        personal: {name, email, phone, location, linkedin, github, portfolio}
        summary: str
        target_role: str
        target_stack: str
        education: [{degree, institution, year, gpa}]
        skills: {technical: [], soft: [], tools: [], languages: []}
        experience: [{title, company, start, end, bullets: []}]
        projects: [{name, tech, description, link}]
        certifications: [{name, issuer, year, link}]
    """
    pdf = ResumePDF()
    pdf.add_page()

    p = data.get("personal", {})

    # ── Header: Name ──
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*ResumePDF.DARK_BLUE)
    pdf.cell(0, 10, p.get("name", "Your Name"), align="C", new_x="LMARGIN", new_y="NEXT")

    # ── Contact line ──
    contact_parts = []
    if p.get("email"):
        contact_parts.append(p["email"])
    if p.get("phone"):
        contact_parts.append(p["phone"])
    if p.get("location"):
        contact_parts.append(p["location"])
    if contact_parts:
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*ResumePDF.LIGHT_GRAY)
        pdf.cell(0, 6, "  |  ".join(contact_parts), align="C", new_x="LMARGIN", new_y="NEXT")

    # ── Links line ──
    link_parts = []
    if p.get("linkedin"):
        link_parts.append(f"LinkedIn: {p['linkedin']}")
    if p.get("github"):
        link_parts.append(f"GitHub: {p['github']}")
    if p.get("portfolio"):
        link_parts.append(f"Portfolio: {p['portfolio']}")
    if link_parts:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*ResumePDF.ACCENT)
        pdf.cell(0, 5, "  |  ".join(link_parts), align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)

    # ── Target Role tag ──
    role = data.get("target_role", "")
    stack = data.get("target_stack", "")
    if role or stack:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*ResumePDF.MEDIUM_BLUE)
        tag = f"Target: {role}" + (f" ({stack})" if stack else "")
        pdf.cell(0, 5, tag, align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    # ── Summary ──
    summary = data.get("summary", "").strip()
    if summary:
        pdf._section_title("Professional Summary")
        pdf._body_text(summary)

    # ── Skills ──
    skills = data.get("skills", {})
    has_skills = any(skills.get(k) for k in ["technical", "soft", "tools", "languages"])
    if has_skills:
        pdf._section_title("Skills")
        for label, key in [("Technical", "technical"), ("Tools & Frameworks", "tools"),
                           ("Soft Skills", "soft"), ("Languages", "languages")]:
            items = skills.get(key, [])
            if items:
                joined = ", ".join(items) if isinstance(items, list) else items
                pdf._label_value(label, joined)
                pdf.ln(1)

    # ── Experience ──
    experience = data.get("experience", [])
    if experience:
        pdf._section_title("Work Experience")
        for exp in experience:
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*ResumePDF.BLACK)
            pdf.cell(0, 6, exp.get("title", ""), new_x="LMARGIN", new_y="NEXT")

            date_str = pdf._date_range(exp.get("start"), exp.get("end"))
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(*ResumePDF.MEDIUM_BLUE)
            company_line = exp.get("company", "")
            if date_str:
                company_line += f"  |  {date_str}"
            pdf.cell(0, 5, company_line, new_x="LMARGIN", new_y="NEXT")

            for bullet in exp.get("bullets", []):
                if bullet.strip():
                    pdf._bullet(bullet.strip())
            pdf.ln(2)

    # ── Projects ──
    projects = data.get("projects", [])
    if projects:
        pdf._section_title("Projects")
        for proj in projects:
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*ResumePDF.BLACK)
            name_line = proj.get("name", "")
            tech = proj.get("tech", "")
            if tech:
                name_line += f"  [{tech}]"
            pdf.cell(0, 6, name_line, new_x="LMARGIN", new_y="NEXT")

            desc = proj.get("description", "").strip()
            if desc:
                pdf._body_text(desc)

            link = proj.get("link", "").strip()
            if link:
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(*ResumePDF.ACCENT)
                pdf.cell(0, 5, link, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

    # ── Education ──
    education = data.get("education", [])
    if education:
        pdf._section_title("Education")
        for edu in education:
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*ResumePDF.BLACK)
            pdf.cell(0, 6, edu.get("degree", ""), new_x="LMARGIN", new_y="NEXT")

            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(*ResumePDF.MEDIUM_BLUE)
            inst_line = edu.get("institution", "")
            year = edu.get("year", "")
            if year:
                inst_line += f"  |  {year}"
            pdf.cell(0, 5, inst_line, new_x="LMARGIN", new_y="NEXT")

            gpa = edu.get("gpa", "")
            if gpa:
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(*ResumePDF.LIGHT_GRAY)
                pdf.cell(0, 5, f"GPA/Percentage: {gpa}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

    # ── Certifications ──
    certs = data.get("certifications", [])
    if certs:
        pdf._section_title("Certifications")
        for cert in certs:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*ResumePDF.BLACK)
            cert_line = cert.get("name", "")
            issuer = cert.get("issuer", "")
            year = cert.get("year", "")
            if issuer:
                cert_line += f" — {issuer}"
            if year:
                cert_line += f" ({year})"
            pdf.cell(0, 5, cert_line, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

    # ── Output ──
    output_dir = os.path.join(os.path.dirname(__file__), "generated_resumes")
    os.makedirs(output_dir, exist_ok=True)

    safe_name = "".join(c if c.isalnum() or c in " _-" else "" for c in p.get("name", "resume"))
    filename = f"{safe_name}_{data.get('target_role', 'general').replace(' ', '_')}.pdf"
    filepath = os.path.join(output_dir, filename)
    pdf.output(filepath)
    return filepath, filename
