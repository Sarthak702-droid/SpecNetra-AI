import os
from typing import Optional
from demo.api.models import Appointment

TEST_USER_EMAIL = os.environ.get("TEST_USER_EMAIL", "tester@example.test")
TEST_USER_PASSWORD = os.environ.get("TEST_USER_PASSWORD", "SecretPassword123!")

SEED_USERS = {
    TEST_USER_EMAIL: TEST_USER_PASSWORD,
}

# In-memory appointments store
_APPOINTMENTS: dict[str, Appointment] = {}
_COUNTER = 5020


def get_next_appointment_id() -> str:
    global _COUNTER
    _COUNTER += 1
    return f"apt_{_COUNTER}"


def save_appointment(appt: Appointment) -> None:
    _APPOINTMENTS[appt.id] = appt


def get_appointment(appt_id: str) -> Optional[Appointment]:
    return _APPOINTMENTS.get(appt_id)


def list_appointments() -> list[Appointment]:
    return list(_APPOINTMENTS.values())


def reset_database() -> None:
    global _COUNTER
    _APPOINTMENTS.clear()
    _COUNTER = 5020
