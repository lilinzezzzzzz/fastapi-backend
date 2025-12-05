from dataclasses import dataclass

from internal.models.user import User
from internal.schemas.user import UserListResponseSchema, UserDetailSchema


@dataclass
class UserListDto:
    total: int
    items: list[User]

    def to_response_schema(self):
        return UserListResponseSchema(
            total=self.total,
            items=[UserDetailSchema(id=item.id, name=item.username, phone=item.phone) for item in self.items]
        )

    def to_dict(self):
        return {
            "total": self.total,
            "items": [item.to_dict() for item in self.items],
            "page": 1,
            "limit": 10
        }
