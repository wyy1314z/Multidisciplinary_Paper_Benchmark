"""Tests for taxonomy loading and navigation."""

import json
import os
import tempfile

import pytest

from crossdisc_extractor.classifier.taxonomy.types import TaxonNode
from crossdisc_extractor.classifier.taxonomy.loader import Taxonomy


@pytest.fixture
def sample_taxonomy_json():
    """Create a temporary taxonomy JSON file."""
    data = {
        "Mathematics": {
            "Algebra": ["Linear Algebra", "Abstract Algebra"],
            "Geometry": ["Differential Geometry", "Algebraic Geometry"],
        },
        "Physics": {
            "Mechanics": ["Classical Mechanics", "Quantum Mechanics"],
            "Optics": ["Wave Optics"],
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
        path = f.name
    yield path
    os.unlink(path)


class TestTaxonNode:
    def test_leaf_node(self):
        node = TaxonNode(name="leaf")
        assert node.is_leaf
        assert node.child_names() == []

    def test_node_with_children(self):
        child = TaxonNode(name="child")
        node = TaxonNode(name="parent", children={"child": child})
        assert not node.is_leaf
        assert node.child_names() == ["child"]


class TestTaxonomy:
    def test_from_json_file(self, sample_taxonomy_json):
        taxo = Taxonomy.from_json_file(sample_taxonomy_json)
        assert set(taxo.level1_options()) == {"Mathematics", "Physics"}

    def test_children_of_root(self, sample_taxonomy_json):
        taxo = Taxonomy.from_json_file(sample_taxonomy_json)
        assert set(taxo.children_of([])) == {"Mathematics", "Physics"}

    def test_children_of_l1(self, sample_taxonomy_json):
        taxo = Taxonomy.from_json_file(sample_taxonomy_json)
        assert set(taxo.children_of(["Mathematics"])) == {"Algebra", "Geometry"}

    def test_children_of_l2(self, sample_taxonomy_json):
        taxo = Taxonomy.from_json_file(sample_taxonomy_json)
        assert set(taxo.children_of(["Mathematics", "Algebra"])) == {"Linear Algebra", "Abstract Algebra"}

    def test_children_of_invalid_path(self, sample_taxonomy_json):
        taxo = Taxonomy.from_json_file(sample_taxonomy_json)
        assert taxo.children_of(["Nonexistent"]) == []

    def test_is_valid_choice(self, sample_taxonomy_json):
        taxo = Taxonomy.from_json_file(sample_taxonomy_json)
        assert taxo.is_valid_choice([], "Mathematics")
        assert not taxo.is_valid_choice([], "Biology")

    def test_depth(self, sample_taxonomy_json):
        taxo = Taxonomy.from_json_file(sample_taxonomy_json)
        assert taxo.depth() == 3

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            Taxonomy.from_json_file("/nonexistent/path.json")

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not json")
            path = f.name
        try:
            with pytest.raises(ValueError, match="Invalid JSON"):
                Taxonomy.from_json_file(path)
        finally:
            os.unlink(path)
