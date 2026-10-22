"""Stable, non-sensitive errors at the HTTP boundary."""


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def invalid(message="Request does not match the API schema."):
    return ApiError(422, "validation_error", message)


def not_found():
    return ApiError(404, "not_found", "Resource not found.")


def conflict(message="Resource changed; retry the request."):
    return ApiError(409, "conflict", message)
