from fastapi import FastAPI

app = FastAPI(title="Captain's Log")

@app.get("/")
def read_root():
    return {"message": "Welcome to Captain's Log"}