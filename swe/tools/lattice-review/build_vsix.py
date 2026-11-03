#!/usr/bin/env python3
"""Package vscode-extension/ as a .vsix without node or vsce."""

import json
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "vscode-extension"

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="{name}" Version="{version}" Publisher="{publisher}"/>
    <DisplayName>{display}</DisplayName>
    <Description xml:space="preserve">{description}</Description>
    <Tags></Tags>
    <Categories>Other</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{engine}"/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value="vscode.git"/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace"/>
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true"/>
  </Assets>
</PackageManifest>
"""

CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json"/>
  <Default Extension=".vsixmanifest" ContentType="text/xml"/>
  <Default Extension=".js" ContentType="application/javascript"/>
  <Default Extension=".md" ContentType="text/markdown"/>
</Types>
"""


def main():
    meta = json.loads((SRC / "package.json").read_text())
    target = HERE / ("%s-%s.vsix" % (meta["name"], meta["version"]))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("extension.vsixmanifest", MANIFEST.format(
            name=meta["name"], version=meta["version"], publisher=meta["publisher"], display=meta["displayName"],
            description=meta["description"], engine=meta["engines"]["vscode"]))
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        for name in ("package.json", "extension.js", "README.md"):
            z.write(SRC / name, "extension/" + name)
    print(target)


if __name__ == "__main__":
    main()
