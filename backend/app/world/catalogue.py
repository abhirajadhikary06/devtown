"""Building catalogue. One line per building: id|name|category|w|d|h. Add a line to extend."""
import colorsys
import zlib

_TABLE = """
home|Cottage|residential|2|2|2
apartment|Apartment block|residential|2|2|4
workshop|Workshop|language|2|2|2
research_lab|Research laboratory|language|3|3|3
commercial_tower|Commercial tower|language|2|2|7
industrial_complex|Industrial complex|language|4|3|3
logistics_hub|Logistics hub|language|4|3|2
enterprise_hq|Enterprise institution|language|3|3|5
factory|Engineering works|language|4|3|3
db_tower|Database tower|language|2|2|8
bigdata_facility|Big-data facility|language|3|3|4
design_studio|Design studio|language|3|2|3
mobile_campus|Mobile campus|language|3|3|3
stats_centre|Statistics centre|language|3|2|3
web_office|Web office|language|2|3|3
utility_station|Utility station|language|1|1|1
xplat_centre|Cross-platform centre|language|3|3|3
mixed_plaza|Mixed-style plaza|language|3|3|2
tech_generic|Technology workshop|tech|2|2|3
backend_campus|Backend campus|tech|3|3|4
creative_commercial|Creative and commercial district|tech|3|3|5
enterprise_campus|Enterprise campus|tech|4|3|5
spark_facility|Distributed computing facility|tech|3|3|4
stream_hub|Streaming infrastructure|tech|3|2|3
automation_tower|Automation tower|tech|2|2|7
data_transform|Data transformation centre|tech|3|2|3
data_warehouse|Data warehouse|tech|3|3|3
lakehouse|Lakehouse complex|tech|4|3|3
doc_storage|Document storage complex|tech|3|2|3
fast_utility|High-speed utility station|tech|1|1|2
search_centre|Search centre|tech|3|2|3
container_facility|Containerization facility|tech|3|2|2
orchestration_centre|Orchestration centre|tech|3|3|4
infra_office|Infrastructure planning office|tech|3|2|3
cloud_district|Cloud infrastructure district|tech|4|4|4
ai_lab|AI research facility|tech|3|3|5
vector_lab|Vector intelligence laboratory|tech|3|2|4
starter_building|Starter building|civic|2|2|2
permit_office|Construction permit office|civic|2|2|3
project_hall|Infrastructure project hall|civic|3|3|4
archive_office|Proposal archive|civic|2|2|2
inspection_centre|Quality inspection facility|civic|3|2|3
consult_centre|Engineering consultation centre|civic|3|2|3
certification_hall|Certification hall|civic|3|3|3
service_office|Community service office|civic|2|2|2
repair_depot|Repair depot|civic|3|2|2
planning_office|City planning office|civic|3|2|3
noticeboard|Public noticeboard|civic|1|1|2
town_hall|Town hall|civic|4|3|4
community_centre|Community centre|civic|3|3|3
logistics_depot|Logistics depot|civic|3|2|2
milestone_marker|Milestone marker|civic|1|1|3
heritage_landmark|Heritage landmark|landmark|3|3|6
bridge_landmark|First bridge landmark|oss|3|1|2
international_district|International district|oss|4|4|4
oss_landmark|Open-source landmark|oss|3|3|7
oss_community_centre|Project community centre|oss|3|3|3
oss_admin|Public administration building|oss|3|3|5
consultancy|Engineering consultancy|oss|3|2|3
satellite_settlement|Satellite settlement|oss|2|2|2
railway_station|Collaboration railway station|oss|4|2|2
neighbourhood_hub|Neighbourhood hub|repo|3|3|3
dev_complex|Development complex|repo|4|4|4
heritage_structure|Heritage structure|landmark|2|2|5
historic_hall|Historic district hall|repo|3|2|3
info_centre|Information centre|repo|2|2|2
public_access_office|Public access office|repo|2|2|2
tourism_office|Tourism office|recognition|3|2|3
famous_landmark|Famous landmark|landmark|3|3|8
community_monument|Community monument|landmark|2|2|6
visitor_plaza|Visitor plaza|recognition|3|3|1
grand_opening_plaza|Grand opening plaza|release|4|3|1
milestone_monument|Milestone monument|landmark|2|2|7
broadcast_tower|Broadcasting tower|release|1|1|9
distribution_warehouse|Distribution warehouse|release|4|3|2
container_hub|Container logistics hub|release|4|3|2
airport_terminal|Transport terminal|release|5|3|3
power_plant|Automated power plant|release|3|3|4
control_tower|Automation control tower|release|2|2|8
library|Public library|quality|3|3|4
knowledge_archive|Knowledge archive|quality|3|2|3
safety_infra|Safety infrastructure|quality|2|2|2
qa_centre|Quality assurance centre|quality|3|3|3
security_station|Security monitoring station|quality|2|2|3
maintenance_facility|Maintenance facility|quality|3|2|2
emergency_centre|Emergency response centre|quality|3|3|3
trust_monument|Trust monument|quality|1|1|5
services_centre|Community services centre|quality|3|2|3
kiosk|Citizen service kiosk|quality|1|1|1
docs_office|Construction documentation office|quality|2|2|2
business_district|Business district|community|4|4|6
tree|Tree|nature|1|1|1
park|Park|nature|2|2|0
streetlight|Street light|nature|1|1|2
road|Road|road|1|1|0
"""
_CAT = {"residential": "#e8c9a5", "language": "#7aa7d9", "tech": "#8d7ad9", "civic": "#d9a066",
        "landmark": "#e0c35f", "oss": "#5fc2a6", "repo": "#c98fb8", "recognition": "#e07a8c",
        "release": "#7fd0e0", "quality": "#9fcf7a", "community": "#d98f7a", "nature": "#5f9f5a",
        "road": "#4a4e57"}
FREE = {"tree", "park", "streetlight", "road"}
BASE_UNLOCKS = {"home", "workshop", "tree", "park", "streetlight", "road", "utility_station"}


def _color(cat, bid):
    base = _CAT[cat].lstrip("#")
    r, g, b = (int(base[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    j = (zlib.crc32(bid.encode()) % 100) / 100
    hh = (hh + (j - .5) * .06) % 1
    ll = min(.8, max(.3, ll + (j - .5) * .12))
    r, g, b = colorsys.hls_to_rgb(hh, ll, ss)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


BUILDINGS: dict[str, dict] = {}
for _line in _TABLE.strip().splitlines():
    bid, name, cat, w, d, h = _line.split("|")
    w, d, h = int(w), int(d), int(h)
    free = bid in FREE
    BUILDINGS[bid] = dict(id=bid, name=name, category=cat, w=w, d=d, h=h, color=_color(cat, bid),
                          coins=0 if free else 10 * w * d + 15 * h,
                          materials=0 if free else 5 * w * d + 5 * h)
BUILDINGS["road"]["coins"] = 2
BUILDINGS["tree"]["coins"] = 1
BUILDINGS["park"]["coins"] = 8
BUILDINGS["streetlight"]["coins"] = 3


def footprint(btype: str, x: int, z: int, rot: int):
    b = BUILDINGS[btype]
    w, d = (b["d"], b["w"]) if rot % 2 else (b["w"], b["d"])
    return [(x + i, z + j) for i in range(w) for j in range(d)], w, d
