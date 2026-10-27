from bernardyn.core.colorscales import COLOR_SCALES, sample_scale


def test_scales_span_full_range_without_repeats():
    for name in COLOR_SCALES:
        colors = sample_scale(name, 100)
        assert len(colors) == 100
        assert colors[0] != colors[-1]
        assert len(set(colors)) > 90


def test_scale_edge_counts():
    assert sample_scale("rainbow", 0) == []
    assert sample_scale("rainbow", 1) == [(230, 0, 0, 255)]
    assert sample_scale("rainbow", 2)[0] == (230, 0, 0, 255)
