from __future__ import annotations

from datetime import datetime
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import get_current_user, get_db
from app.models import Clinic, Doctor, ClinicService, KVKKDisclosureVersion, User, RoleName
from app.services.clinical_service import ensure_clinic_access


router = APIRouter(prefix="/clinic/admin", tags=["clinic_admin"])


def check_admin_access(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role.name != RoleName.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem yalnızca yönetici (admin) yetkisi gerektirir."
        )
    return current_user


class BrandingUpdateSchema(BaseModel):
    headline: str | None = None
    sub_headline: str | None = None
    logo_url: str | None = None
    primary_color: str | None = None
    accent_color: str | None = None
    contact_phone: str | None = None
    public_address: str | None = None


class DoctorCreateSchema(BaseModel):
    full_name: str
    specialty: str
    is_active: bool = True


class DoctorResponseSchema(BaseModel):
    id: int
    clinic_id: int
    full_name: str
    specialty: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ServiceCreateSchema(BaseModel):
    name: str
    description: str | None = None
    is_active: bool = True


class ServiceResponseSchema(BaseModel):
    id: int
    clinic_id: int
    name: str
    description: str | None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DisclosureCreateSchema(BaseModel):
    version: str
    disclosure_text: str
    is_active: bool = True


class DisclosureResponseSchema(BaseModel):
    id: int
    clinic_id: int
    version: str
    disclosure_text: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.get("/branding")
def get_branding(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_access),
) -> dict[str, Any]:
    clinic = ensure_clinic_access(db, current_user)
    branding = (clinic.settings_json or {}).get("branding", {})
    return {"branding": branding}


@router.patch("/branding")
def patch_branding(
    payload: BrandingUpdateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_access),
) -> dict[str, Any]:
    clinic = ensure_clinic_access(db, current_user)
    settings = dict(clinic.settings_json or {})
    branding = dict(settings.get("branding", {}))
    
    # Update branding dict
    for key, value in payload.model_dump(exclude_unset=True).items():
        branding[key] = value
        
    settings["branding"] = branding
    clinic.settings_json = settings
    db.add(clinic)
    db.commit()
    db.refresh(clinic)
    return {"branding": branding}


@router.get("/doctors", response_model=list[DoctorResponseSchema])
def get_doctors(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_access),
) -> list[Doctor]:
    clinic = ensure_clinic_access(db, current_user)
    doctors = list(db.scalars(select(Doctor).where(Doctor.clinic_id == clinic.id)).all())
    return doctors


@router.post("/doctors", response_model=DoctorResponseSchema)
def post_doctor(
    payload: DoctorCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_access),
) -> Doctor:
    clinic = ensure_clinic_access(db, current_user)
    doctor = Doctor(
        clinic_id=clinic.id,
        full_name=payload.full_name,
        specialty=payload.specialty,
        is_active=payload.is_active,
    )
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return doctor


@router.patch("/doctors/{id}", response_model=DoctorResponseSchema)
def patch_doctor(
    id: int,
    payload: DoctorCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_access),
) -> Doctor:
    clinic = ensure_clinic_access(db, current_user)
    doctor = db.scalars(select(Doctor).where(Doctor.clinic_id == clinic.id, Doctor.id == id)).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Hekim bulunamadı.")
    
    doctor.full_name = payload.full_name
    doctor.specialty = payload.specialty
    doctor.is_active = payload.is_active
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return doctor


@router.delete("/doctors/{id}")
def delete_doctor(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_access),
) -> dict[str, bool]:
    clinic = ensure_clinic_access(db, current_user)
    doctor = db.scalars(select(Doctor).where(Doctor.clinic_id == clinic.id, Doctor.id == id)).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Hekim bulunamadı.")
    
    db.delete(doctor)
    db.commit()
    return {"ok": True}


@router.get("/services", response_model=list[ServiceResponseSchema])
def get_services(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_access),
) -> list[ClinicService]:
    clinic = ensure_clinic_access(db, current_user)
    services = list(db.scalars(select(ClinicService).where(ClinicService.clinic_id == clinic.id)).all())
    return services


@router.post("/services", response_model=ServiceResponseSchema)
def post_service(
    payload: ServiceCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_access),
) -> ClinicService:
    clinic = ensure_clinic_access(db, current_user)
    service = ClinicService(
        clinic_id=clinic.id,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.patch("/services/{id}", response_model=ServiceResponseSchema)
def patch_service(
    id: int,
    payload: ServiceCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_access),
) -> ClinicService:
    clinic = ensure_clinic_access(db, current_user)
    service = db.scalars(select(ClinicService).where(ClinicService.clinic_id == clinic.id, ClinicService.id == id)).first()
    if not service:
        raise HTTPException(status_code=404, detail="Hizmet bulunamadı.")
    
    service.name = payload.name
    service.description = payload.description
    service.is_active = payload.is_active
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.delete("/services/{id}")
def delete_service(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_access),
) -> dict[str, bool]:
    clinic = ensure_clinic_access(db, current_user)
    service = db.scalars(select(ClinicService).where(ClinicService.clinic_id == clinic.id, ClinicService.id == id)).first()
    if not service:
        raise HTTPException(status_code=404, detail="Hizmet bulunamadı.")
    
    db.delete(service)
    db.commit()
    return {"ok": True}


@router.get("/disclosures", response_model=list[DisclosureResponseSchema])
def get_disclosures(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_access),
) -> list[KVKKDisclosureVersion]:
    clinic = ensure_clinic_access(db, current_user)
    disclosures = list(db.scalars(
        select(KVKKDisclosureVersion)
        .where(KVKKDisclosureVersion.clinic_id == clinic.id)
        .order_by(KVKKDisclosureVersion.created_at.desc())
    ).all())
    return disclosures


@router.post("/disclosures", response_model=DisclosureResponseSchema)
def post_disclosure(
    payload: DisclosureCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_access),
) -> KVKKDisclosureVersion:
    clinic = ensure_clinic_access(db, current_user)
    
    # If this new disclosure is active, deactivate all other disclosures for this clinic
    if payload.is_active:
        active_disclosures = db.scalars(
            select(KVKKDisclosureVersion).where(
                KVKKDisclosureVersion.clinic_id == clinic.id,
                KVKKDisclosureVersion.is_active == True
            )
        ).all()
        for disc in active_disclosures:
            disc.is_active = False
            db.add(disc)
            
    disclosure = KVKKDisclosureVersion(
        clinic_id=clinic.id,
        version=payload.version,
        disclosure_text=payload.disclosure_text,
        is_active=payload.is_active,
    )
    db.add(disclosure)
    db.commit()
    db.refresh(disclosure)
    return disclosure
