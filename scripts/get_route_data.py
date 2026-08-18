import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Add server root to sys.path for app module imports
server_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(server_root))

from app.models.structure.route import Route
from app.models.structure.route_segment import RouteSegment
from app.models.structure.segment import Segment
from app.models.structure.stop import Stop


async def get_route_details(db: AsyncSession, route_id: int, tenant_id: UUID):
    print(f"--- Detalles para Ruta ID: {route_id}, Tenant ID: {tenant_id} ---")

    # 1. Get Route details
    route = await db.scalar(select(Route).where(Route.id == route_id, Route.tenant_id == tenant_id).limit(1))
    if not route:
        print(f"Ruta con ID {route_id} y Tenant ID {tenant_id} no encontrada.")
        return

    print(f"\n[Ruta]")
    print(f"  ID: {route.id}")
    print(f"  Nombre: {route.name}")
    print(f"  Válida: {route.is_valid}")
    print(f"  Activa: {route.is_active}")
    print(f"  Código: {route.route_code}")
    print(f"  Color: {route.color}")
    print(f"  Tenant ID: {route.tenant_id}")

    # 2. Get RouteSegments for the route
    route_segments = (await db.scalars(
        select(RouteSegment)
        .where(RouteSegment.route_id == route_id, RouteSegment.tenant_id == tenant_id)
        .order_by(RouteSegment.order_index.asc())
    )).all()

    if not route_segments:
        print(f"\nNo se encontraron RouteSegments para la Ruta ID {route_id}.")
        return

    print(f"\n[RouteSegments ({len(route_segments)} encontrados)]")
    segment_ids = [rs.segment_id for rs in route_segments]
    segments_map = {s.id: s for s in (await db.scalars(select(Segment).where(Segment.id.in_(segment_ids)))).all()}

    stop_ids = []
    for seg in segments_map.values():
        stop_ids.append(seg.from_stop_id)
        stop_ids.append(seg.to_stop_id)
    stops_map = {st.id: st for st in (await db.scalars(select(Stop).where(Stop.id.in_(stop_ids)))).all()}

    for rs in route_segments:
        segment = segments_map.get(rs.segment_id)
        if not segment:
            print(f"  - ERROR: Segmento {rs.segment_id} no encontrado para RouteSegment {rs.id}")
            continue

        from_stop = stops_map.get(segment.from_stop_id)
        to_stop = stops_map.get(segment.to_stop_id)

        print(f"  - RouteSegment ID: {rs.id}")
        print(f"    Order Index: {rs.order_index}")
        print(f"    Segment ID: {segment.id}")
        print(f"      From Stop: {from_stop.name if from_stop else 'N/A'} (ID: {segment.from_stop_id})")
        print(f"      To Stop: {to_stop.name if to_stop else 'N/A'} (ID: {segment.to_stop_id})")
        print(f"      Waypoints: {segment.waypoints}")
        print(f"      Polyline: {segment.polyline}")
        print(f"      Distance (m): {segment.distance_m}")
        print(f"      Is Active: {segment.is_active}")

    print("\n--- Fin de detalles ---")


def load_env(server_root: Path) -> None:
    env_path = server_root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def main():
    setup_dir = Path(__file__).resolve().parent
    server_root = setup_dir.parent.parent
    sys.path.append(str(server_root))
    load_env(server_root)

    from app.core.settings import settings

    engine = create_async_engine(settings.database_url_async)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    # TODO: Replace with actual route_id and tenant_id from your database
    # You can get these from your panel UI or by querying your DB directly
    # Example:
    # route_id_to_check = 1
    # tenant_id_to_check = UUID("your-tenant-id-here")

    # For demonstration, using placeholder values.
    # You MUST change these to your actual values.
    list_all_routes_with_segments = True # <--- CAMBIA ESTE VALOR a False para especificar una ruta

    route_id_to_check = 1 # <--- CAMBIA ESTE VALOR si list_all_routes_with_segments es False
    tenant_id_to_check = UUID("c84f1b55-0ad4-4c03-ba9d-6806423fd134") # <--- CAMBIA ESTE VALOR si list_all_routes_with_segments es False

    try:
        async with async_session() as db:
            if list_all_routes_with_segments:
                print("Listando todas las rutas con RouteSegments...")
                routes_with_segments = (await db.scalars(
                    select(Route)
                    .join(RouteSegment, Route.id == RouteSegment.route_id)
                    .distinct()
                    .order_by(Route.id.asc())
                )).all()
                if not routes_with_segments:
                    print("No se encontraron rutas con RouteSegments.")
                    return

                for route in routes_with_segments:
                    await get_route_details(db, route.id, route.tenant_id)
            else:
                if route_id_to_check == 1 and tenant_id_to_check == UUID("c84f1b55-0ad4-4c03-ba9d-6806423fd134"):
                    print("ADVERTENCIA: Usando valores de ejemplo para route_id y tenant_id.")
                    print("Por favor, edita el script 'get_route_data.py' con los valores reales de tu base de datos.")
                    print("Ejecuta 'rebuild_db.py' para asegurarte de tener datos si no estás seguro.")
                    return
                await get_route_details(db, route_id_to_check, tenant_id_to_check)
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
