"""Inbound push receiver for PDHC dispatch.

Accepts FHIR Bundles pushed from request.pdhc, validates the
X-Push-Secret header, and logs the receipt. Stores nothing
persistent yet — 1177 is primarily a forms intake service; this
endpoint exists so the PDHC dispatch handshake completes.
"""
import logging
from flask import Blueprint, request, jsonify, current_app

logger = logging.getLogger(__name__)

inbound_bp = Blueprint("inbound", __name__)


@inbound_bp.route("/inbound/push", methods=["POST"])
def receive_push():
    expected = current_app.config.get("PUSH_SECRET")
    if not expected:
        return jsonify(code="not_configured",
                       message="Push reception not configured"), 503

    got = request.headers.get("X-Push-Secret")
    if not got or got != expected:
        logger.warning("Push rejected: bad X-Push-Secret from %s",
                       request.remote_addr)
        return jsonify(code="unauthenticated",
                       message="Invalid push secret"), 401

    bundle = request.get_json(silent=True)
    if not bundle or bundle.get("resourceType") != "Bundle":
        return jsonify(code="bad_request",
                       message="Expected FHIR Bundle"), 400

    receipt_token = None
    for tag in bundle.get("meta", {}).get("tag", []):
        if tag.get("code") == "receipt_token":
            receipt_token = tag.get("display")
            break

    logger.info("1177 inbound push accepted: receipt_token=%s entries=%d",
                receipt_token, len(bundle.get("entry", [])))

    return jsonify(status="accepted", receipt_token=receipt_token), 202
