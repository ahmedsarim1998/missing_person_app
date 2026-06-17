from app import create_app
from extensions import db
from models import MissingPerson, MatchAlert

app = create_app()

with app.app_context():
    try:
        person = MissingPerson.query.filter(MissingPerson.name.ilike("ahmed sarim")).first()
        if person:
            # Delete related MatchAlerts first
            MatchAlert.query.filter_by(missing_person_id=person.id).delete()
            
            # Delete the person
            db.session.delete(person)
            db.session.commit()
            print(f"Successfully deleted {person.name} and related records.")
        else:
            print("Person 'ahmed sarim' not found.")
    except Exception as e:
        db.session.rollback()
        print(f"Error: {e}")
