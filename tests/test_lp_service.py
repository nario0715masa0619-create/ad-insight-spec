"""
Tests for LPService

Test coverage:
- Local HTML file parsing (2 samples: JP + EN)
- URL input validation (without actual fetch)
- Component extraction: FV copy, CTA, offer, form fields
- Fallback extraction (h1 → h2 → p)
- Section detection: hero, social proof, FAQ
- Error handling: file not found, invalid URL, parse error
"""

import pytest
import tempfile
from pathlib import Path

from app.services.lp_service import LPService
from app.services.base_service import ValidationError, ProcessingError


class TestLPService:
    """Test suite for LPService"""
    
    @pytest.fixture
    def service(self):
        """Create LPService instance"""
        return LPService()
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test HTML files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    # ===== Input Validation Tests =====
    
    def test_validate_input_url(self, service):
        """Test validation of HTTP URL"""
        assert service.validate_input("https://example.com/lp") is True
    
    def test_validate_input_http_url(self, service):
        """Test validation of HTTP URL"""
        assert service.validate_input("http://example.com/lp") is True
    
    def test_validate_input_file_path(self, service, temp_dir):
        """Test validation of local file path"""
        test_file = Path(temp_dir) / "test.html"
        test_file.write_text("<html><body>Test</body></html>")
        
        assert service.validate_input(str(test_file)) is True
    
    def test_validate_input_invalid_url(self, service):
        """Test validation rejects invalid URL"""
        with pytest.raises(ValidationError):
            service.validate_input("ftp://example.com")
    
    def test_validate_input_nonexistent_file(self, service):
        """Test validation rejects non-existent file"""
        with pytest.raises(ValidationError):
            service.validate_input("/nonexistent/file.html")
    
    def test_validate_input_empty_string(self, service):
        """Test validation rejects empty input"""
        with pytest.raises(ValidationError):
            service.validate_input("")
    
    def test_validate_input_not_string(self, service):
        """Test validation rejects non-string input"""
        with pytest.raises(ValidationError):
            service.validate_input(123)
    
    # ===== Local HTML Parsing Tests (Japanese) =====
    
    def test_execute_japanese_lp_full_structure(self, service, temp_dir):
        """Test parsing of full Japanese LP"""
        html_content = """
        <html>
        <head><meta charset="utf-8"></head>
        <body>
            <section class="hero">
                <img src="hero.jpg" alt="Hero">
                <h1>簡単LP作成ツール</h1>
                <p>2分でプロレベルのLPが完成。コーディング知識は不要です。</p>
            </section>
            
            <section class="offer">
                <p>今なら初月50%割引。30日間無料トライアル。</p>
            </section>
            
            <section class="testimonials">
                <h2>お客様の声</h2>
                <blockquote>成約率が3倍になりました！</blockquote>
            </section>
            
            <form>
                <input type="text" name="name" placeholder="お名前">
                <input type="email" name="email" placeholder="メール">
                <textarea name="message"></textarea>
                <button type="submit">今すぐ始める</button>
            </form>
        </body>
        </html>
        """
        
        test_file = Path(temp_dir) / "lp_ja.html"
        test_file.write_text(html_content, encoding='utf-8')
        
        result = service.execute(str(test_file))
        
        assert result["fv_copy"] == "簡単LP作成ツール"
        assert result["form_present"] is True
        assert result["form_fields_count"] == 3
        assert result["has_hero_section"] is True
        assert result["has_social_proof"] is True
        assert "50%割引" in result["offer"] or "割引" in str(result["offer"])
    
    def test_execute_japanese_lp_extract_cta(self, service, temp_dir):
        """Test CTA extraction from Japanese LP"""
        html_content = """
        <html>
        <body>
            <h1>サービス</h1>
            <p>説明文</p>
            <button>今すぐ始める</button>
        </body>
        </html>
        """
        
        test_file = Path(temp_dir) / "lp_ja_cta.html"
        test_file.write_text(html_content, encoding='utf-8')
        
        result = service.execute(str(test_file))
        
        assert result["primary_cta"] == "今すぐ始める"
    
    # ===== Local HTML Parsing Tests (English) =====
    
    def test_execute_english_lp_full_structure(self, service, temp_dir):
        """Test parsing of full English LP"""
        html_content = """
        <html>
        <head><meta charset="utf-8"></head>
        <body>
            <section class="hero">
                <img src="hero.jpg" alt="Hero">
                <h1>Easy LP Builder</h1>
                <p>Create professional landing pages in 2 minutes. No coding required.</p>
            </section>
            
            <section class="offer">
                <p>Get 50% off first month. Free 30-day trial.</p>
            </section>
            
            <section class="testimonials">
                <h2>Customer Reviews</h2>
                <blockquote>Conversion rate increased by 3x!</blockquote>
            </section>
            
            <form>
                <input type="text" name="fullname" placeholder="Full Name">
                <input type="email" name="email_address" placeholder="Email">
                <button type="submit">Start Free Trial</button>
            </form>
        </body>
        </html>
        """
        
        test_file = Path(temp_dir) / "lp_en.html"
        test_file.write_text(html_content, encoding='utf-8')
        
        result = service.execute(str(test_file))
        
        assert result["fv_copy"] == "Easy LP Builder"
        assert result["form_present"] is True
        assert result["form_fields_count"] == 2
        assert result["has_hero_section"] is True
        assert result["has_social_proof"] is True
        assert "50%" in result["offer"] or "off" in result["offer"].lower()
    
    def test_execute_english_lp_form_fields(self, service, temp_dir):
        """Test form field extraction from English LP"""
        html_content = """
        <html>
        <body>
            <form>
                <input type="text" name="username" placeholder="Username">
                <input type="email" name="user_email" placeholder="Email">
                <input type="tel" name="phone" placeholder="Phone">
                <textarea name="message" placeholder="Message"></textarea>
            </form>
        </body>
        </html>
        """
        
        test_file = Path(temp_dir) / "lp_en_form.html"
        test_file.write_text(html_content)
        
        result = service.execute(str(test_file))
        
        assert result["form_fields_count"] == 4
        assert "username" in result["form_field_names"]
        assert "user_email" in result["form_field_names"]
    
    # ===== Extraction Logic Tests =====
    
    def test_extract_fv_copy_h1_priority(self, service, temp_dir):
        """Test that h1 is prioritized for FV copy"""
        html_content = """
        <html>
        <body>
            <h1>Main Title</h1>
            <h2>Subtitle</h2>
            <p>Paragraph</p>
        </body>
        </html>
        """
        
        test_file = Path(temp_dir) / "test_h1.html"
        test_file.write_text(html_content)
        
        result = service.execute(str(test_file))
        assert result["fv_copy"] == "Main Title"
    
    def test_extract_fv_copy_h2_fallback(self, service, temp_dir):
        """Test h2 fallback when h1 missing"""
        html_content = """
        <html>
        <body>
            <h2>Subtitle Only</h2>
            <p>Paragraph</p>
        </body>
        </html>
        """
        
        test_file = Path(temp_dir) / "test_h2.html"
        test_file.write_text(html_content)
        
        result = service.execute(str(test_file))
        assert result["fv_copy"] == "Subtitle Only"
    
    def test_extract_fv_copy_paragraph_fallback(self, service, temp_dir):
        """Test paragraph fallback when h1/h2 missing"""
        html_content = """
        <html>
        <body>
            <p>This is a meaningful paragraph with enough content.</p>
        </body>
        </html>
        """
        
        test_file = Path(temp_dir) / "test_p.html"
        test_file.write_text(html_content)
        
        result = service.execute(str(test_file))
        assert "meaningful paragraph" in result["fv_copy"]
    
    def test_extract_all_ctas(self, service, temp_dir):
        """Test extraction of multiple CTAs"""
        html_content = """
        <html>
        <body>
            <button>Sign Up Now</button>
            <button>Learn More</button>
            <a href="#">Start Free Trial</a>
            <input type="submit" value="Get Started">
        </body>
        </html>
        """
        
        test_file = Path(temp_dir) / "test_ctas.html"
        test_file.write_text(html_content)
        
        result = service.execute(str(test_file))
        
        assert len(result["detected_ctas"]) >= 2
        assert "Sign Up Now" in result["detected_ctas"]
    
    def test_estimate_form_scroll_depth(self, service, temp_dir):
        """Test form scroll depth estimation"""
        html_content = """
        <html>
        <body>
            <h1>Title</h1>
            <p>Content</p>
            <form><input type="text" name="email"><button>Submit</button></form>
        </body>
        </html>
        """
        
        test_file = Path(temp_dir) / "test_form_depth.html"
        test_file.write_text(html_content)
        
        result = service.execute(str(test_file))
        
        assert result["estimated_scroll_depth_for_form"] in ["above_fold", "mid_page", "below_fold"]
    
    # ===== Feature Detection Tests =====
    
    def test_has_faq_section_detection(self, service, temp_dir):
        """Test FAQ section detection"""
        html_content = """
        <html>
        <body>
            <h1>Title</h1>
            <section class="faq">
                <h2>Frequently Asked Questions</h2>
            </section>
        </body>
        </html>
        """
        
        test_file = Path(temp_dir) / "test_faq.html"
        test_file.write_text(html_content)
        
        result = service.execute(str(test_file))
        assert result["has_faq_section"] is True
    
    def test_missing_form_returns_zero_fields(self, service, temp_dir):
        """Test behavior when form is missing"""
        html_content = """
        <html>
        <body>
            <h1>No Form Here</h1>
            <p>Just content</p>
        </body>
        </html>
        """
        
        test_file = Path(temp_dir) / "test_no_form.html"
        test_file.write_text(html_content)
        
        result = service.execute(str(test_file))
        
        assert result["form_present"] is False
        assert result["form_fields_count"] == 0
    
    # ===== Error Handling Tests =====
    
    def test_execute_file_not_found(self, service):
        """Test execute with non-existent file"""
        with pytest.raises(ValidationError):
            service.execute("/nonexistent/file.html")
    
    def test_execute_invalid_input_type(self, service):
        """Test execute with invalid input type"""
        with pytest.raises(ValidationError):
            service.execute(123)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
