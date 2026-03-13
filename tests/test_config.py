"""tests/test_config.py - 配置模块单元测试"""
import threading
import pytest
from crossdisc_extractor.config import (
    PipelineConfig,
    LanguageMode,
    set_language_mode,
    get_language_mode,
)


class TestPipelineConfig:
    def test_default_values(self):
        cfg = PipelineConfig()
        assert cfg.language_mode == "chinese"
        assert cfg.temperature_struct == 0.2
        assert cfg.seed == 42

    def test_frozen_immutable(self):
        cfg = PipelineConfig()
        with pytest.raises(Exception):
            cfg.language_mode = "original"  # frozen dataclass 不允许修改

    def test_with_overrides_returns_new_object(self):
        cfg = PipelineConfig()
        cfg2 = cfg.with_overrides(language_mode="original", seed=0)
        assert cfg2.language_mode == "original"
        assert cfg2.seed == 0
        # 原对象不变
        assert cfg.language_mode == "chinese"
        assert cfg.seed == 42

    def test_apply_to_thread(self):
        cfg = PipelineConfig(language_mode="original")
        cfg.apply_to_thread()
        assert get_language_mode() == LanguageMode.ORIGINAL
        # 恢复
        set_language_mode("chinese")


class TestThreadLocalLanguageMode:
    def test_default_is_chinese(self):
        assert get_language_mode() == LanguageMode.CHINESE

    def test_set_and_get(self):
        set_language_mode("original")
        assert get_language_mode() == LanguageMode.ORIGINAL
        set_language_mode("chinese")
        assert get_language_mode() == LanguageMode.CHINESE

    def test_thread_isolation(self):
        """不同线程的语言模式互不干扰"""
        results = {}

        def worker_a():
            set_language_mode("original")
            import time; time.sleep(0.05)
            results["a"] = get_language_mode()

        def worker_b():
            set_language_mode("chinese")
            import time; time.sleep(0.05)
            results["b"] = get_language_mode()

        t_a = threading.Thread(target=worker_a)
        t_b = threading.Thread(target=worker_b)
        t_a.start(); t_b.start()
        t_a.join(); t_b.join()

        assert results["a"] == LanguageMode.ORIGINAL
        assert results["b"] == LanguageMode.CHINESE

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            set_language_mode("invalid_mode")
