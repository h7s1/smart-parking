"""Gate route (Figures 4 and 7): used by the gate simulator, not by the web pages."""
from flask import jsonify

from . import bp, validation
from .guards import gate_key_required
from ..logic import gate


@bp.post("/gate/events")
@gate_key_required
def gate_event():
    """FR-09 to FR-11, SR-20, NFR-02.

    Body: {"direction": "ENTRY" or "EXIT", "plate": "ABC1234"}.
    The answer is only ALLOW or DENY. The plate is never sent back, stored or
    logged (PR-01).
    """
    data = validation.json_body()
    direction = validation.choice(data, "direction", "Direction", gate.DIRECTIONS)
    plate = validation.plate(data)                         # SR-17
    return jsonify(decision=gate.decide(plate, direction))
