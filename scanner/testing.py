#!/usr/bin/env python
"""
"XMP:RegionAreaY": ["0.54359006211180116","0.84621532091097307","0.21942028985507245","0.59319254658385101","0.48045962732919251"],
  "XMP:RegionAreaW": ["0.18313043478260871","0.072447204968944107","0.088546583850931671","0.10363975155279503","0.074459627329192535"],
  "XMP:RegionAreaX": ["0.78073291925465838","0.16593788819875777","0.48490683229813669",0.3465527950310559,0.2605217391304348],
  "XMP:RegionAreaH": ["0.25953623188405794","0.10321325051759833",0.1262608695652174,"0.14630227743271218","0.10521739130434782"],
  "XMP:RegionAreaUnit": ["normalized","normalized","normalized","normalized","normalized"],
  "XMP:RegionType": ["Face","Face","Face","Face","Face"],
  "XMP:RegionExtensionsAngleInfoYaw": 315,
  "XMP:RegionExtensionsAngleInfoRoll": 270,
  "XMP:RegionExtensionsConfidenceLevel": 99,
  "XMP:RegionExtensionsTimeStamp": 10710898096788,
  "XMP:RegionExtensionsFaceID": 29,
  "XMP:RegionAppliedToDimensionsH": 1932,
  "XMP:RegionAppliedToDimensionsW": 2576,
"""

from scanner.exiftool import ExifTool
from wand.image import Image
from wand.drawing import Drawing
from wand.color import Color


PATHS = (
    "../web/public/albums/facetest.jpg",
    "../web/public/albums/facetest2.jpg",
    "../web/public/albums/facetest_names.jpg"
)
TAGS_TO_EXTRACT = (
    "XMP:Region*"
)

for p in PATHS:
    img = Image(filename=p)

    info = ExifTool().process_files(p, tags=TAGS_TO_EXTRACT)[0]

    num_faces = len(info["XMP:RegionType"])
    names = info.get("XMP:RegionName")
    descriptions = info.get("XMP:RegionDescription")
    img_w = int(info["XMP:RegionAppliedToDimensionsW"])
    img_h = int(info["XMP:RegionAppliedToDimensionsH"])

    for face in range(num_faces):
        y, w, x, h = [float(info["XMP:RegionArea{}".format(x)][face]) for x in ("Y", "W", "X", "H")]
        y *= img_h
        w *= img_w
        x *= img_w
        h *= img_h

        # wand vs. exif coordinates
        y, x = x, y

        with Drawing() as draw:
            draw.stroke_width = 10
            draw.stroke_color = Color('white')
            draw.fill_color = Color('transparent')
            draw.polygon([(y-h, x-w), (y+h, x-w), (y+h, x+w), (y-h, x+w)])
            draw.font = "Courier New"
            draw.fill_color = Color("white")
            if names:
                draw.font_size = 130
                draw.font_style = "normal"
                draw.text(int(y-h), int(x), names[face])
            if descriptions:
                draw.font_size = 80
                draw.font_style = "italic"
                draw.text(int(y-h), int(x+w/2), descriptions[face])
            draw(img)
    img.save(filename="{}.faces.jpg".format(p))

