from dataclasses import dataclass

from internal.models.user import User
from internal.schemas.user import UserDetailSchema, UserListResponseSchema


@dataclass(frozen=True, slots=True, kw_only=True)
class UserListDto:
    total: int
    items: list[User]

    def to_response_schema(self):
        return UserListResponseSchema(
            total=self.total,
            items=[UserDetailSchema(id=item.id, name=str(item.username), phone=str(item.phone)) for item in self.items],
        )

    def to_dict(self):
        return {"total": self.total, "items": [item.to_dict() for item in self.items], "page": 1, "limit": 10}
