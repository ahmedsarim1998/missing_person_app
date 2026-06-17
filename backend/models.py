from extensions import db
from datetime import datetime

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    middle_name = db.Column(db.String(50), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='user') # guest, user, admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class MissingPerson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    national_id = db.Column(db.String(50), nullable=True)
    last_location = db.Column(db.String(200), nullable=True)
    identifiers = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='active') # active, solved
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    embedding_blob = db.Column(db.PickleType, nullable=True) # Storing numpy array directly
    photo_path = db.Column(db.String(200), nullable=True) # Path to main display photo
    last_location_updated_at = db.Column(db.DateTime, nullable=True) # When last_location was last changed
    last_location_source = db.Column(db.String(50), nullable=True) # 'manual' or 'facebook'

class MatchAlert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    missing_person_id = db.Column(db.Integer, db.ForeignKey('missing_person.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    confidence = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending') # pending, confirmed, rejected
    snapshot_path = db.Column(db.String(200), nullable=True)  # cropped live frame for side-by-side review
    resolved_by = db.Column(db.String(80), nullable=True)     # admin username who confirmed/rejected
    resolved_at = db.Column(db.DateTime, nullable=True)       # when it was resolved

    person = db.relationship('MissingPerson', backref='matches')

class FacebookSighting(db.Model):
    # Audit log of location updates derived from Facebook posts.
    # Every name match is recorded here (even those below the auto-update bar),
    # and previous_location is kept so an auto-update can be traced/reverted.
    id = db.Column(db.Integer, primary_key=True)
    missing_person_id = db.Column(db.Integer, db.ForeignKey('missing_person.id'), nullable=False)
    post_id = db.Column(db.String(100), unique=True) # FB post id -> dedupe / skip reprocessing
    post_url = db.Column(db.String(300), nullable=True)
    post_text = db.Column(db.Text, nullable=True)
    matched_name = db.Column(db.String(100), nullable=True) # the case name we matched against
    match_score = db.Column(db.Float, nullable=True) # fuzzy match score 0-100
    previous_location = db.Column(db.String(200), nullable=True) # value before this update
    new_location = db.Column(db.String(200), nullable=True) # extracted last-seen location
    applied = db.Column(db.Boolean, default=False) # whether last_location was actually changed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    person = db.relationship('MissingPerson', backref='sightings')
