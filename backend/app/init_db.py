import logging
from backend.app.core.database import engine, Base
import backend.app.models # Ensure all models are registered with Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    logger.info("Khởi tạo tất cả bảng cơ sở dữ liệu...")
    Base.metadata.create_all(bind=engine)
    logger.info("Cơ sở dữ liệu đã được khởi tạo thành công!")

if __name__ == "__main__":
    init_db()
