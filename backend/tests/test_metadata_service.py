import pytest
from app.services.metadata_service import MetadataService

def test_generate_asset_id():
    service = MetadataService()
    
    # 同一コンテンツ・同一プラットフォームなら同じID
    content1 = b"dummy file content"
    platform1 = "tiktok"
    id1 = service._generate_asset_id(platform1, content1)
    id2 = service._generate_asset_id(platform1, content1)
    assert id1 == id2
    
    # コンテンツが異なれば違うID
    content2 = b"dummy file content 2"
    id3 = service._generate_asset_id(platform1, content2)
    assert id1 != id3
    
    # プラットフォームが異なれば違うID
    platform2 = "meta"
    id4 = service._generate_asset_id(platform2, content1)
    assert id1 != id4
    
    # IDのフォーマット確認
    assert id1.startswith("asset_tiktok_")
    assert len(id1) == len("asset_tiktok_") + 16
