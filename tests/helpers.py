"""Faux résultats ffprobe pour tester sans fichier vidéo."""
from vidcompare.probe import parse_probe


def video(w=3840, h=2160, codec="hevc", bit_rate=None, transfer="smpte2084", pix="yuv420p10le", dv=None):
    s = {"codec_type": "video", "codec_name": codec, "width": w, "height": h,
         "avg_frame_rate": "24000/1001", "pix_fmt": pix, "color_transfer": transfer}
    if bit_rate:
        s["bit_rate"] = str(bit_rate)
    if dv:
        s["side_data_list"] = [{"side_data_type": "DOVI configuration record", "dv_profile": dv[0],
                                "dv_bl_signal_compatibility_id": dv[1]}]
    return s


def audio(codec, channels, profile=None, lang="eng", bit_rate=None):
    s = {"codec_type": "audio", "codec_name": codec, "channels": channels, "tags": {"language": lang}}
    if profile:
        s["profile"] = profile
    if bit_rate:
        s["bit_rate"] = str(bit_rate)
    return s


def make(name, streams, size_gb=50.0, minutes=120):
    dur = minutes * 60
    data = {"format": {"format_name": "matroska,webm", "duration": str(dur),
                       "size": str(int(size_gb * 1e9)),
                       "bit_rate": str(int(size_gb * 1e9 * 8 / dur))},
            "streams": streams}
    return parse_probe(data, "C:/films/" + name, int(size_gb * 1e9))
