import os
from fastapi import APIRouter, Depends, HTTPException
from demo.api.auth import get_current_user
from demo.api.database import get_appointment, get_next_appointment_id, list_appointments, save_appointment
from demo.api.models import Appointment, AppointmentCreate

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


@router.post("", response_model=Appointment, status_code=201)
async def create_appointment(
    req: AppointmentCreate,
    user: str = Depends(get_current_user),
):
    if not req.patient_name.strip():
        raise HTTPException(status_code=422, detail="patient_name cannot be empty")

    appt_id = get_next_appointment_id()
    appt = Appointment(
        id=appt_id,
        patient_name=req.patient_name,
        starts_at=req.starts_at,
        reason=req.reason,
        status="confirmed",
    )
    save_appointment(appt)
    return appt


@router.get("", response_model=list[Appointment])
async def list_user_appointments(user: str = Depends(get_current_user)):
    return list_appointments()


@router.get("/{appointment_id}", response_model=Appointment)
async def get_single_appointment(
    appointment_id: str,
    user: str = Depends(get_current_user),
):
    # Intentional defect switch (PRD §11 & tech stack §5.4):
    bug_mode = os.environ.get("DEMO_BUG_MODE", "")
    if bug_mode == "hide_created_appointment":
        raise HTTPException(status_code=404, detail="Appointment not found (intentional demo bug)")

    appt = get_appointment(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appt
