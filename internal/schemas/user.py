from typing import Annotated

from pydantic import Field, BaseModel


class UserReqSchema(BaseModel):
    name: Annotated[..., Field(min_length=1, max_length=20)]
