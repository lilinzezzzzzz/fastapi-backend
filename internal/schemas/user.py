from pydantic import Field
from typing import Annotated

from pkg.orm_tool.model_mixin import ModelMixin


class UserReqSchema(ModelMixin):
    name: Annotated[..., Field(min_length=1, max_length=20)]
