from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Mock Legacy Bank")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

MEMBERS = {
    "12345": {
        "name": "Alex Example",
        "accounts": [
            {"type": "Checking", "masked_number": "•••• 1001", "balance": "$1,250.00"},
            {"type": "Savings", "masked_number": "•••• 2001", "balance": "$8,430.42"},
        ],
    },
    "67890": {
        "name": "Jordan Sample",
        "accounts": [
            {"type": "Checking", "masked_number": "•••• 1002", "balance": "$93.18"},
        ],
    },
    "40800": {
        "name": "Casey Session",
        "accounts": [
            {"type": "Checking", "masked_number": "•••• 4080", "balance": "$408.00"},
        ],
    },
    "50000": {
        "name": "Taylor Retry",
        "accounts": [
            {"type": "Checking", "masked_number": "•••• 5000", "balance": "$500.00"},
        ],
    },
    "77777": {
        "name": "Morgan Dialog",
        "accounts": [
            {"type": "Checking", "masked_number": "•••• 7777", "balance": "$777.77"},
        ],
    },
}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="search.html")


@app.get("/members")
async def search_member(member_id: str = Query(min_length=1)) -> RedirectResponse:
    if member_id == "50000":
        await asyncio.sleep(0.5)
    return RedirectResponse(url=f"/members/{member_id}", status_code=303)


@app.get("/members/{member_id}", response_class=HTMLResponse)
async def member_details(
    request: Request,
    member_id: str,
    resumed: bool = False,
    retried: bool = False,
    continued: bool = False,
) -> HTMLResponse:
    if member_id == "40300":
        return templates.TemplateResponse(
            request=request,
            name="message.html",
            context={
                "code": "permission-denied",
                "heading": "Permission denied",
                "message": "Your operator role cannot view this member.",
            },
            status_code=403,
        )
    if member_id == "40800" and not resumed:
        return templates.TemplateResponse(
            request=request,
            name="message.html",
            context={
                "code": "session-expired",
                "heading": "Session expired",
                "message": "Sign in again before continuing.",
                "action_label": "Resume session",
                "action_url": "/members/40800?resumed=true",
            },
            status_code=401,
        )
    if member_id == "50000" and not retried:
        return templates.TemplateResponse(
            request=request,
            name="message.html",
            context={
                "code": "transient-load-error",
                "heading": "Temporary application error",
                "message": "The member service is temporarily unavailable.",
                "action_label": "Retry",
                "action_url": "/members/50000?retried=true",
            },
            status_code=503,
        )
    if member_id == "77777" and not continued:
        return templates.TemplateResponse(
            request=request,
            name="message.html",
            context={
                "code": "known-interstitial",
                "heading": "Informational notice",
                "message": "Acknowledge the notice before viewing this member.",
                "action_label": "Continue",
                "action_url": "/members/77777?continued=true",
            },
        )
    if member_id == "66666":
        return templates.TemplateResponse(
            request=request,
            name="message.html",
            context={
                "code": "unknown-application-error",
                "heading": "Unknown application error",
                "message": "The application returned an unrecognized state.",
            },
            status_code=500,
        )
    member = MEMBERS.get(member_id)
    if member is None:
        return templates.TemplateResponse(
            request=request,
            name="message.html",
            context={
                "code": "member-not-found",
                "heading": "Member not found",
                "message": f"No member exists with ID {member_id}.",
            },
            status_code=404,
        )
    return templates.TemplateResponse(
        request=request,
        name="member.html",
        context={"member_id": member_id, "member": member},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
