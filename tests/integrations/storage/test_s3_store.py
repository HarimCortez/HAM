"""R2ObjectStore (S2.4a) against a mocked boto3 client — no network, no moto dependency.
Pins the contract (bucket/key/method args) and the 404-vs-error head_object mapping."""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from ham.integrations.storage.s3 import R2ObjectStore


@pytest.fixture
def s3_settings(settings):
    settings.HAM_S3_BUCKET = "ham-media"
    settings.HAM_S3_ENDPOINT_URL = "https://example.r2.cloudflarestorage.com"
    settings.HAM_S3_ACCESS_KEY_ID = "AKIDTEST"
    settings.HAM_S3_SECRET_ACCESS_KEY = "secret"
    settings.HAM_S3_REGION = "auto"
    return settings


def test_missing_settings_raise_clear_runtime_error(settings):
    settings.HAM_S3_BUCKET = ""
    settings.HAM_S3_ENDPOINT_URL = ""
    settings.HAM_S3_ACCESS_KEY_ID = ""
    settings.HAM_S3_SECRET_ACCESS_KEY = ""
    with pytest.raises(RuntimeError, match="HAM_S3_BUCKET"):
        R2ObjectStore()


@patch("ham.integrations.storage.s3.boto3.client")
def test_presign_put_calls_generate_presigned_url_for_put(mock_client_factory, s3_settings):
    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = "https://signed.example/put"
    mock_client_factory.return_value = mock_client

    store = R2ObjectStore()
    result = store.presign_put(
        "abc123", content_type="image/jpeg", max_bytes=1000, expires_in=dt.timedelta(minutes=15)
    )

    assert result.url == "https://signed.example/put"
    assert result.key == "abc123"
    mock_client.generate_presigned_url.assert_called_once()
    args, kwargs = mock_client.generate_presigned_url.call_args
    assert args[0] == "put_object"
    assert kwargs["Params"]["Bucket"] == "ham-media"
    assert kwargs["Params"]["Key"] == "abc123"
    assert kwargs["Params"]["ContentType"] == "image/jpeg"
    assert kwargs["ExpiresIn"] == 900


@patch("ham.integrations.storage.s3.boto3.client")
def test_presign_get_calls_generate_presigned_url_for_get(mock_client_factory, s3_settings):
    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = "https://signed.example/get"
    mock_client_factory.return_value = mock_client

    store = R2ObjectStore()
    url = store.presign_get("abc123", expires_in=dt.timedelta(seconds=60))

    assert url == "https://signed.example/get"
    args, kwargs = mock_client.generate_presigned_url.call_args
    assert args[0] == "get_object"
    assert kwargs["ExpiresIn"] == 60


@patch("ham.integrations.storage.s3.boto3.client")
def test_head_returns_none_for_missing_object(mock_client_factory, s3_settings):
    mock_client = MagicMock()
    mock_client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
    )
    mock_client_factory.return_value = mock_client

    store = R2ObjectStore()
    assert store.head("missing") is None


@patch("ham.integrations.storage.s3.boto3.client")
def test_head_reraises_non_404_errors(mock_client_factory, s3_settings):
    mock_client = MagicMock()
    mock_client.head_object.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "Internal Error"}}, "HeadObject"
    )
    mock_client_factory.return_value = mock_client

    store = R2ObjectStore()
    with pytest.raises(ClientError):
        store.head("whatever")


@patch("ham.integrations.storage.s3.boto3.client")
def test_head_returns_meta_for_existing_object(mock_client_factory, s3_settings):
    mock_client = MagicMock()
    mock_client.head_object.return_value = {"ContentLength": 42, "ContentType": "video/mp4"}
    mock_client_factory.return_value = mock_client

    store = R2ObjectStore()
    meta = store.head("exists")
    assert meta is not None
    assert meta.size == 42
    assert meta.content_type == "video/mp4"


@patch("ham.integrations.storage.s3.boto3.client")
def test_delete_is_idempotent_by_contract(mock_client_factory, s3_settings):
    mock_client = MagicMock()
    mock_client_factory.return_value = mock_client
    store = R2ObjectStore()
    store.delete("gone")
    mock_client.delete_object.assert_called_once_with(Bucket="ham-media", Key="gone")


@patch("ham.integrations.storage.s3.boto3.client")
def test_copy_uses_server_side_copy(mock_client_factory, s3_settings):
    mock_client = MagicMock()
    mock_client_factory.return_value = mock_client
    store = R2ObjectStore()
    store.copy("src-key", "dest-key")
    mock_client.copy_object.assert_called_once_with(
        Bucket="ham-media",
        Key="dest-key",
        CopySource={"Bucket": "ham-media", "Key": "src-key"},
    )


@patch("ham.integrations.storage.s3.boto3.client")
def test_get_object_raises_file_not_found_on_missing_key(mock_client_factory, s3_settings):
    mock_client = MagicMock()
    mock_client.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "nope"}}, "GetObject"
    )
    mock_client_factory.return_value = mock_client

    store = R2ObjectStore()
    with pytest.raises(FileNotFoundError):
        store.get_object("nope")
