import rasterio
import numpy as np
import matplotlib.pyplot as plt

# Load NDVI GeoTIFF
with rasterio.open("NDVI_Point_Map.tif") as src:
    ndvi = src.read(1)
    bounds = src.bounds

# Clean invalid values
ndvi = np.clip(ndvi, 0, 1)

# Save as PNG
plt.imshow(ndvi, cmap="RdYlGn")
plt.colorbar(label="NDVI")
plt.axis("off")
plt.savefig("ndvi_map.png", bbox_inches="tight", dpi=200)
plt.close()

print("PNG created: ndvi_map.png")
