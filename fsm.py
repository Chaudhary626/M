from aiogram.fsm.state import State, StatesGroup

class UploadVideoFSM(StatesGroup):
    waiting_for_title = State()
    waiting_for_thumbnail = State()
    waiting_for_duration = State()
    waiting_for_link = State()

class SubmitProofFSM(StatesGroup):
    waiting_for_task_id = State()
    waiting_for_proof = State()

class RemoveVideoFSM(StatesGroup):
    waiting_for_video_select = State()