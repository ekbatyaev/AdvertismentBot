from pydantic import BaseModel

class BotPermissions(BaseModel):
    permission_to_read: bool
    bot_channel_status: str

class SendAnalysis(BaseModel):
    analysis_sent_status: bool
    status_description: str

class DateValidation(BaseModel):
    validation_status: bool
    status_description: str
