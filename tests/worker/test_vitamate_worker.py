from unittest.mock import Mock

from app.client.dto import (
    VitamateAnalysisJob,
    VitamateCallbackRequest,
    VitamateCallbackResponse,
)
from app.core.exceptions import SpringVitamateTemporaryError, VitamateAiGenerateError
from app.worker.vitamate_worker import VitamateRedisWorker


ANALYSIS_ID = 11
ATTEMPT_ID = "63a556c0-a8c2-4715-8dce-93cb9f367118"
MESSAGE_ID = "message-1"


def test_handle_message_sends_completed_callback_and_acks():
    worker, spring_client, processor, ack = _worker_with_fakes()
    job = _job()
    completed_callback = _callback("COMPLETED", result="분석 결과")

    spring_client.get_analysis_job.return_value = job
    processor.analyze.return_value = completed_callback
    spring_client.send_callback.return_value = _callback_response("COMPLETED")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    spring_client.send_callback.assert_called_once_with(
        analysis_id=ANALYSIS_ID,
        callback=completed_callback,
    )
    ack.assert_called_once_with(MESSAGE_ID)


def test_handle_message_sends_failed_callback_from_processor_and_acks():
    worker, spring_client, processor, ack = _worker_with_fakes()
    job = _job()
    failed_callback = _callback("FAILED", error_message="AI 분석 처리 중 오류가 발생했습니다.")

    spring_client.get_analysis_job.return_value = job
    processor.analyze.return_value = failed_callback
    spring_client.send_callback.return_value = _callback_response("FAILED")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    spring_client.send_callback.assert_called_once_with(
        analysis_id=ANALYSIS_ID,
        callback=failed_callback,
    )
    ack.assert_called_once_with(MESSAGE_ID)


def test_handle_message_sends_failed_callback_when_processing_crashes_and_acks():
    worker, spring_client, processor, ack = _worker_with_fakes()

    spring_client.get_analysis_job.return_value = _job()
    processor.analyze.side_effect = RuntimeError("unexpected processor error")
    spring_client.send_callback.return_value = _callback_response("FAILED")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    sent_callback = spring_client.send_callback.call_args.kwargs["callback"]
    assert sent_callback.analysis_status == "FAILED"
    assert sent_callback.error_message == "AI analysis processing failed"
    ack.assert_called_once_with(MESSAGE_ID)


def test_handle_message_sends_failed_callback_when_ai_generation_fails_and_acks():
    worker, spring_client, processor, ack = _worker_with_fakes()

    spring_client.get_analysis_job.return_value = _job()
    processor.analyze.side_effect = VitamateAiGenerateError("gemini failed")
    spring_client.send_callback.return_value = _callback_response("FAILED")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    sent_callback = spring_client.send_callback.call_args.kwargs["callback"]
    assert sent_callback.analysis_status == "FAILED"
    assert sent_callback.error_message == "AI analysis failed"
    ack.assert_called_once_with(MESSAGE_ID)


def test_handle_message_does_not_ack_when_callback_has_temporary_failure():
    worker, spring_client, processor, ack = _worker_with_fakes()

    spring_client.get_analysis_job.return_value = _job()
    processor.analyze.return_value = _callback("COMPLETED", result="분석 결과")
    spring_client.send_callback.side_effect = SpringVitamateTemporaryError("temporary")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    ack.assert_not_called()


def test_handle_message_sends_failed_callback_when_job_response_is_invalid_and_acks():
    # get_analysis_job 응답이 계약과 안 맞아 파싱에 실패해도(예: 필수 필드 누락) worker 전체가
    # 죽지 않고 FAILED로 확정 후 ack해야 한다. job이 없으므로 message의 id를 그대로 써야 한다.
    worker, spring_client, _, ack = _worker_with_fakes()

    spring_client.get_analysis_job.side_effect = ValueError("prompt field missing")
    spring_client.send_callback.return_value = _callback_response("FAILED")

    worker._handle_message(MESSAGE_ID, _raw_payload())

    spring_client.send_callback.assert_called_once_with(
        analysis_id=ANALYSIS_ID,
        callback=_callback("FAILED", error_message="분석 작업 조회 응답이 올바르지 않습니다."),
    )
    ack.assert_called_once_with(MESSAGE_ID)


def test_handle_message_acks_invalid_message():
    worker, _, _, ack = _worker_with_fakes()

    worker._handle_message(MESSAGE_ID, {"analysisId": "invalid"})

    ack.assert_called_once_with(MESSAGE_ID)


def _worker_with_fakes():
    # Redis 연결 없이 worker 처리 흐름만 검증하기 위해 필요한 협력 객체만 주입합니다.
    worker = VitamateRedisWorker.__new__(VitamateRedisWorker)
    spring_client = Mock()
    processor = Mock()
    ack = Mock()

    worker._spring_client = spring_client
    worker._processor = processor
    worker._ack = ack

    return worker, spring_client, processor, ack


def _raw_payload() -> dict[str, object]:
    return {
        "analysisId": ANALYSIS_ID,
        "attemptId": ATTEMPT_ID,
        "retryCount": 0,
    }


def _job() -> VitamateAnalysisJob:
    return VitamateAnalysisJob(
        analysisId=ANALYSIS_ID,
        attemptId=ATTEMPT_ID,
        reviewType="COST_REPORT",
        reviewCategoryCodes=["COST_RESULT"],
        prompt="기준 문서와 비교하여 핵심 기술 요구사항과 위험 요소를 검토해줘.",
        reviewTemplates=[
            {
                "reviewType": "COST_REPORT",
                "categoryCode": "COST_RESULT",
                "categoryName": "I. 원가계산 결과",
                "promptTemplate": "원가 총액과 항목별 합계가 일치하는지 검토합니다.",
                "templateVersion": "COST_REPORT_V1",
            }
        ],
        searchScope={
            "projectId": 1,
            "blockId": 900001,
            "fileVersionIds": [900001],
        },
        documents=[
            {
                "fileVersionId": 900001,
                "fileName": "제안요청서.pdf",
                "documentRole": "TARGET",
                "chunks": [
                    {
                        "documentChunkId": 1,
                        "chromaId": "chunk-1",
                        "pageNumber": 1,
                        "excerpt": "스마트시티 통합 관제와 보안 인증이 필요합니다.",
                    }
                ],
            }
        ],
    )


def _callback(
    analysis_status: str,
    result: str | None = None,
    error_message: str | None = None,
) -> VitamateCallbackRequest:
    return VitamateCallbackRequest(
        attemptId=ATTEMPT_ID,
        analysisStatus=analysis_status,
        result=result,
        citations=[],
        errorMessage=error_message,
    )


def _callback_response(analysis_status: str) -> VitamateCallbackResponse:
    return VitamateCallbackResponse(
        accepted=True,
        analysisId=ANALYSIS_ID,
        analysisStatus=analysis_status,
        reason=None,
    )
