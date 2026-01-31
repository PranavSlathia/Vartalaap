from fastapi_crudrouter import SQLAlchemyCRUDRouter
from src.db.models import Reservation
from src.schemas.reservation import Reservation as ReservationSchema
from src.db.session import get_session


class ReservationCreate(ReservationSchema):
    id: None = None
    created_at: None = None
    updated_at: None = None


class ReservationUpdate(ReservationSchema):
    party_size: int | None = None
    reservation_date: str | None = None
    reservation_time: str | None = None


reservation_router = SQLAlchemyCRUDRouter(
    schema=ReservationSchema,
    create_schema=ReservationCreate,
    update_schema=ReservationUpdate,
    db_model=Reservation,
    db=get_session,
    prefix="reservations",
    tags=["Reservations"],
    delete_all_route=False,
)
