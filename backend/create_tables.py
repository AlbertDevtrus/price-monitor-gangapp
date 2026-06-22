from models.alert import Alert
from models.base import Base, engine
from models.platform import Platform
from models.price_history import PriceHistory
from models.product import Product


def create_tables():
    print("Creando tablas...")
    Base.metadata.create_all(bind=engine)
    print("Tablas creadas exitosamente!")

    print("\nTablas en la base de datos:")
    for table in Base.metadata.sorted_tables:
        print(f"  - {table.name}")


if __name__ == "__main__":
    create_tables()
