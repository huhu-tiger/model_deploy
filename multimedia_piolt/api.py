

import traceback
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app_context import logger
from routers.video.video_edit import router as video_edit_router

app = FastAPI()

# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": str(exc), "trace": traceback.format_exc().splitlines()},
    )

app.include_router(video_edit_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
