import json
from dataclasses import replace

from bernardyn.core.models import Dataset, GraphDocument, SeriesStyle, SeriesView
from bernardyn.template.graph_templates import apply_template, load_template, save_template


def test_template_is_human_readable_and_contains_no_dataset_references(tmp_path):
    dataset = Dataset(q=[1, 2], intensity=[3, 4])
    graph = GraphDocument(
        title="Journal style",
        series=(
            SeriesView(
                dataset_id=dataset.id,
                style=SeriesStyle(color=(1, 2, 3, 255), line_width=2.5),
            ),
        ),
        width_px=1800,
        height_px=1200,
    )
    path = save_template(tmp_path / "journal", graph, "Journal")
    document = json.loads(path.read_text(encoding="utf-8"))
    assert path.name.endswith(".bernardyn-template.json")
    assert document["graph"]["series"] == []
    assert dataset.id not in path.read_text(encoding="utf-8")

    other = Dataset(q=[1, 2], intensity=[5, 6])
    target = GraphDocument(series=(SeriesView(dataset_id=other.id),))
    applied = apply_template(target, load_template(path))
    assert applied.series[0].dataset_id == other.id
    assert applied.series[0].style.color == (1, 2, 3, 255)
    assert (applied.width_px, applied.height_px) == (1800, 1200)


def test_template_application_keeps_target_graph_identity():
    target = GraphDocument()
    template = GraphDocument(title="Template")
    document = {
        "format": "BERNARDYN_GRAPH_TEMPLATE",
        "schema_version": 1,
        "name": "Template",
        "graph": template.to_dict(),
        "series_styles": [],
        "transform_id": "raw",
        "transform_parameters": {},
    }
    applied = apply_template(replace(target, title="Before"), document)
    assert applied.id == target.id
    assert applied.title == "Template"
