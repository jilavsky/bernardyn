import numpy as np
import pytest

from bernardyn.core.models import (
    Annotation,
    AnnotationKind,
    Dataset,
    GraphDocument,
    PlotSeries,
    SeriesView,
)
from bernardyn.core.transforms import TransformRegistry, builtin_transforms, resolve_series
from bernardyn.io.sources import ScatteringRecord, SourceRegistry
from bernardyn.renderers.registry import RendererRegistration, RendererRegistry


@pytest.fixture
def dataset():
    return Dataset(
        q=np.array([0.0, 1.0, 2.0, 3.0]),
        intensity=np.array([4.0, 8.0, 16.0, -2.0]),
        uncertainty=np.array([0.4, 0.8, 1.6, 0.2]),
        dq=np.array([0.01, 0.02, 0.03, 0.04]),
        label="sample",
    )


def test_dataset_arrays_are_immutable_and_validated(dataset):
    assert not dataset.q.flags.writeable
    with pytest.raises(ValueError):
        Dataset(q=[1, 2], intensity=[1])
    with pytest.raises(ValueError):
        dataset.q[0] = 5
    with pytest.raises(ValueError, match="empty"):
        Dataset(q=[], intensity=[])


def test_nonfinite_unsorted_and_duplicate_q_are_masked_without_reordering():
    source = Dataset(
        q=[2.0, 1.0, 1.0, np.nan, np.inf],
        intensity=[4.0, 3.0, 2.0, 1.0, 1.0],
    )
    view = SeriesView(dataset_id=source.id, transform_id="raw")
    result = builtin_transforms().get("raw").apply(source, view)
    np.testing.assert_allclose(result.x, [2, 1, 1])
    np.testing.assert_array_equal(result.source_indices, [0, 1, 2])
    assert result.dy is None and result.dx is None
    assert any("outside" in warning for warning in result.warnings)


@pytest.mark.parametrize(
    ("transform_id", "expected_x", "expected_y"),
    [
        ("raw", [0, 1, 2, 3], [4, 8, 16, -2]),
        ("guinier", [0, 1, 4], np.log([4, 8, 16])),
        ("guinier_rod", [1, 4], np.log([8, 32])),
        ("guinier_sheet", [1, 4], np.log([8, 64])),
        ("kratky", [0, 1, 2, 3], [0, 8, 64, -18]),
        ("porod", [0, 1, 16, 81], [0, 8, 256, -162]),
        ("porod2", [0, 1, 2, 3], [0, 8, 256, -162]),
        ("porod3", [0, 1, 2, 3], [0, 8, 128, -54]),
        ("zimm", [0, 1, 4], [0.25, 0.125, 0.0625]),
        ("debye_bueche", [0, 1, 4], np.sqrt([0.25, 0.125, 0.0625])),
    ],
)
def test_irena_transform_formulas(dataset, transform_id, expected_x, expected_y):
    registry = builtin_transforms()
    view = SeriesView(dataset_id=dataset.id, transform_id=transform_id)
    result = registry.get(transform_id).apply(dataset, view)
    np.testing.assert_allclose(result.x, expected_x)
    np.testing.assert_allclose(result.y, expected_y)


def test_uncertainty_and_dq_propagation(dataset):
    result = builtin_transforms().get("guinier").apply(
        dataset, SeriesView(dataset_id=dataset.id, transform_id="guinier")
    )
    np.testing.assert_allclose(result.dy, [0.1, 0.1, 0.1])
    np.testing.assert_allclose(result.dx, [0, 0.04, 0.12])


@pytest.mark.parametrize(
    ("transform_id", "parameters", "expected_dx", "expected_dy"),
    [
        ("raw", {}, 0.1, 0.4),
        ("guinier", {}, 0.4, 0.1),
        ("guinier_rod", {}, 0.4, 0.1),
        ("guinier_sheet", {}, 0.4, 0.1),
        ("kratky", {}, 0.1, 1.6),
        ("dimensionless_kratky", {"I0": 2, "Rg": 3}, 0.1, 7.2),
        ("porod", {}, 3.2, 6.4),
        ("porod2", {}, 0.1, 6.4),
        ("porod3", {}, 0.1, 3.2),
        ("zimm", {}, 0.4, 0.025),
        ("debye_bueche", {}, 0.4, 0.025),
    ],
)
def test_every_transform_uncertainty_formula(
    transform_id, parameters, expected_dx, expected_dy
):
    source = Dataset(q=[2.0], intensity=[4.0], uncertainty=[0.4], dq=[0.1])
    view = SeriesView(
        dataset_id=source.id,
        transform_id=transform_id,
        transform_parameters=parameters,
    )
    result = builtin_transforms().get(transform_id).apply(source, view)
    np.testing.assert_allclose(result.dx, [expected_dx])
    np.testing.assert_allclose(result.dy, [expected_dy])


def test_dimensionless_kratky_requires_parameters(dataset):
    transform = builtin_transforms().get("dimensionless_kratky")
    with pytest.raises(ValueError, match="requires"):
        transform.apply(dataset, SeriesView(dataset_id=dataset.id, transform_id=transform.id))
    result = transform.apply(
        dataset,
        SeriesView(
            dataset_id=dataset.id,
            transform_id=transform.id,
            transform_parameters={"I0": 4, "Rg": 2},
        ),
    )
    np.testing.assert_allclose(result.x, [1, 2, 3])
    np.testing.assert_allclose(result.y, [8, 64, -18])


def test_log_mask_removes_points_individually(dataset):
    view = SeriesView(dataset_id=dataset.id)
    result = resolve_series(dataset, view, builtin_transforms(), x_log=True, y_log=True)
    np.testing.assert_allclose(result.x, [1, 2])
    assert any("logarithmic" in warning for warning in result.warnings)


def test_graph_document_json_round_trip(dataset):
    annotation = Annotation(AnnotationKind.ARROW, (1, 2), end=(3, 4), text="note")
    graph = GraphDocument(
        title="Publication",
        series=(SeriesView(dataset_id=dataset.id),),
        annotations=(annotation,),
    )
    restored = GraphDocument.from_dict(graph.to_dict())
    assert restored == graph
    assert restored.annotations[0].kind is AnnotationKind.ARROW


def test_series_multiplier_and_range(dataset):
    view = SeriesView(dataset_id=dataset.id, q_range=(1, 2), multiplier=2, offset=1)
    result = builtin_transforms().get("raw").apply(dataset, view)
    np.testing.assert_allclose(result.y, [17, 33])
    np.testing.assert_array_equal(result.source_indices, [1, 2])


def test_renderer_registry_accepts_extension_without_main_window_change(qapp):
    from PySide6.QtWidgets import QWidget

    registry = RendererRegistry()
    registry.register(RendererRegistration("dummy", "Dummy", "1.0", QWidget))
    widget = registry.get("dummy").create()
    assert isinstance(widget, QWidget)
    widget.close()


def test_source_and_transform_registries_accept_extensions(dataset, tmp_path):
    class DummySource:
        id = "dummy-source"
        suffixes = (".dummy",)

        def discover(self, path):
            return []

        def load(self, location, **options):
            return ScatteringRecord(q=[1], intensity=[2])

    class DummyTransform:
        id = "dummy-transform"
        name = "Dummy"
        version = "1.0"
        parameters = ()
        default_x_label = "x"
        default_y_label = "y"
        default_x_log = False
        default_y_log = False

        def apply(self, source, view):
            return PlotSeries(
                series_id=view.id,
                dataset_id=source.id,
                x=source.q,
                y=source.intensity,
                transform_id=self.id,
                transform_version=self.version,
            )

    sources = SourceRegistry()
    sources.register(DummySource())
    assert sources.adapter_for(tmp_path / "anything.dummy").id == "dummy-source"
    transforms = TransformRegistry()
    transforms.register(DummyTransform())
    view = SeriesView(dataset_id=dataset.id, transform_id="dummy-transform")
    result = transforms.get("dummy-transform").apply(dataset, view)
    assert result.transform_id == "dummy-transform"
