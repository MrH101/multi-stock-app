"""Order state machine: who may move an order to which status."""
from multistock_common.auth import OrgType

from .models import OrderStatus as S

# (from_status) -> {org_type allowed to act: [to_statuses]}
TRANSITIONS: dict[S, dict[OrgType, list[S]]] = {
    S.SUBMITTED: {OrgType.SUPPLIER: [S.ACCEPTED, S.REJECTED], OrgType.PHARMACY: [S.CANCELLED]},
    S.ACCEPTED: {OrgType.SUPPLIER: [S.DISPATCHED, S.CANCELLED], OrgType.PHARMACY: [S.CANCELLED]},
    S.DISPATCHED: {OrgType.SUPPLIER: [S.DELIVERED], OrgType.PHARMACY: [S.DELIVERED]},
}

RELEASES_STOCK = {S.REJECTED, S.CANCELLED}
COMMITS_STOCK = {S.DISPATCHED}
OPEN = {S.SUBMITTED, S.ACCEPTED, S.DISPATCHED}
# statuses whose value counts against a pharmacy's budget
COMMITTED_SPEND = {S.SUBMITTED, S.ACCEPTED, S.DISPATCHED, S.DELIVERED}


def allowed(current: S, org_type: OrgType) -> list[S]:
    return TRANSITIONS.get(current, {}).get(org_type, [])
