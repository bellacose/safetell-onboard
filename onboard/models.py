"""Storage for the onboarding workbench. Its own database: nothing here touches SafeTell's.
SQLite by default (ONBOARD_DB_URL to point at Postgres)."""
from __future__ import annotations
import datetime as dt, os
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

now = lambda: dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class Engagement(Base):
    """One customer being assessed and onboarded."""
    __tablename__ = 'engagements'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default='assessment')  # assessment | setup | delivered
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    uploads: Mapped[list['Upload']] = relationship(back_populates='engagement', cascade='all, delete-orphan', order_by='Upload.id')
    documents: Mapped[list['SourceDocument']] = relationship(back_populates='engagement', cascade='all, delete-orphan', order_by='SourceDocument.id')
    assessment: Mapped['Assessment | None'] = relationship(back_populates='engagement', cascade='all, delete-orphan', uselist=False)


class Upload(Base):
    """A file the customer sent, stored as sent."""
    __tablename__ = 'uploads'
    id: Mapped[int] = mapped_column(primary_key=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey('engagements.id'))
    kind: Mapped[str] = mapped_column(String(40))  # see UPLOAD_KINDS
    filename: Mapped[str] = mapped_column(String(300))
    path: Mapped[str] = mapped_column(String(500))
    no_ai: Mapped[bool] = mapped_column(Boolean, default=False)  # customer said: do not send to AI
    form_c_ref: Mapped[str | None] = mapped_column(String(10))   # D01..D29 when it answers a Form C row
    mapping: Mapped[dict | None] = mapped_column(JSON)            # column mapping + header row for spreadsheets
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    engagement: Mapped[Engagement] = relationship(back_populates='uploads')


UPLOAD_KINDS = {
    'company_manual': 'Company safety manual', 'owner_spec': 'Owner safety spec', 'vendor_list': 'Vendor / subcontractor list',
    'ca_log': 'Corrective action log', 'injury_log': 'Injury log', 'hours': 'Man-hours', 'checklist': 'Inspection checklist',
    'permits': 'Permits', 'coi': 'Certificate of insurance', 'workbook': 'Filled SafeTell workbook', 'other': 'Other',
}


class SourceDocument(Base):
    """A manual or spec split into numbered paragraphs for review."""
    __tablename__ = 'source_documents'
    id: Mapped[int] = mapped_column(primary_key=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey('engagements.id'))
    upload_id: Mapped[int | None] = mapped_column(ForeignKey('uploads.id'))
    kind: Mapped[str] = mapped_column(String(30))  # company_manual | owner_spec
    title: Mapped[str] = mapped_column(String(300))
    project_code: Mapped[str | None] = mapped_column(String(50))  # owner specs belong to a project
    text: Mapped[str] = mapped_column(Text)
    paragraphs: Mapped[list] = mapped_column(JSON)
    review_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_provider: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    engagement: Mapped[Engagement] = relationship(back_populates='documents')
    drafts: Mapped[list['Draft']] = relationship(back_populates='document', cascade='all, delete-orphan', order_by='Draft.id')
    skips: Mapped[list['Skip']] = relationship(back_populates='document', cascade='all, delete-orphan')


class Draft(Base):
    __tablename__ = 'drafts'
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey('source_documents.id'))
    paragraph_ref: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(300))
    requirement_text: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(50))
    high_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    quote: Mapped[str | None] = mapped_column(Text)
    quote_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    accepted_without_quote: Mapped[bool] = mapped_column(Boolean, default=False)
    unmatched_numbers: Mapped[list] = mapped_column(JSON, default=list)
    origin: Mapped[str] = mapped_column(String(10), default='ai')  # ai | manual
    status: Mapped[str] = mapped_column(String(12), default='pending')  # pending | accepted | rejected
    note: Mapped[str | None] = mapped_column(Text)
    document: Mapped[SourceDocument] = relationship(back_populates='drafts')


class Skip(Base):
    """A paragraph the reviewer marked as not a requirement."""
    __tablename__ = 'skips'
    __table_args__ = (UniqueConstraint('document_id', 'paragraph_ref'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey('source_documents.id'))
    paragraph_ref: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(Text)
    document: Mapped[SourceDocument] = relationship(back_populates='skips')


class Assessment(Base):
    """Forms A-C answers (customer) and the scores computed from them."""
    __tablename__ = 'assessments'
    id: Mapped[int] = mapped_column(primary_key=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey('engagements.id'), unique=True)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    engagement: Mapped[Engagement] = relationship(back_populates='assessment')


def make_session(url: str | None = None):
    url = url or os.environ.get('ONBOARD_DB_URL', 'sqlite:///' + os.path.join(os.environ.get('ONBOARD_DATA', 'data'), 'onboard.db'))
    if url.startswith('sqlite:///') and url != 'sqlite:///:memory:':
        os.makedirs(os.path.dirname(url[len('sqlite:///'):]) or '.', exist_ok=True)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
