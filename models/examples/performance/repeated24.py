from cadgen import build123d as bd
from cadgen import step


@step(out="repeated24.step")
def repeated24():
    box = bd.Box(12, 10, 8)
    cylinder = bd.Cylinder(5, 8)
    parts = []
    for index in range(12):
        x = (index % 6) * 22
        y = (index // 6) * 34
        box_copy = box.moved(bd.Location((x, y, 0)))
        box_copy.label = f"box_{index + 1}"
        parts.append(box_copy)

        cylinder_copy = cylinder.moved(bd.Location((x, y + 17, 0)))
        cylinder_copy.label = f"cylinder_{index + 1}"
        parts.append(cylinder_copy)

    return bd.Compound(obj=parts, children=parts, label="repeated_24")


if __name__ == "__main__":
    repeated24()
