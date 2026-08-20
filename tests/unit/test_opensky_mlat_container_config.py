"""Tests for the OpenSky container-owned MLAT configuration."""

from pathlib import Path


ADSB_ROOT = (
    Path(__file__).parents[2]
    / "src/modules/adsb-feeder/filesystem/root/opt/adsb"
)


def test_primary_opensky_container_receives_global_mlat_policy():
    compose = (ADSB_ROOT / "os.yml").read_text()

    assert "ENABLE_MLAT=${MLAT_ENABLE}" in compose
    assert "MLAT_PRIVACY=${MLAT_PRIVACY}" in compose
    assert "MLAT_RESULTS_BEASTHOST=ultrafeeder" in compose
    assert "MLAT_RESULTS_BEASTPORT=31004" in compose


def test_stage2_opensky_container_receives_stage_mlat_policy():
    compose = (ADSB_ROOT / "os_stage2_template.yml").read_text()

    assert "ENABLE_MLAT=${MLAT_ENABLE_STAGE2NUM}" in compose
    assert "MLAT_PRIVACY=${MLAT_PRIVACY}" in compose
    assert "MLAT_RESULTS_BEASTHOST=uf_STAGE2NUM" in compose
    assert "MLAT_RESULTS_BEASTPORT=31004" in compose


def test_opensky_mlat_endpoint_is_not_owned_by_adsb_im():
    for filename in ("os.yml", "os_stage2_template.yml"):
        compose = (ADSB_ROOT / filename).read_text()
        assert "mlat-server.opensky-network.org" not in compose
