// Bounded animation fixture: every occurrence moves while shared geometry
// and instanced draws remain reusable. Copy beside repeated24.step for QA.
export const clips = {
  cycle: {
    duration: 2,
    loop: true,
    update(t, model) {
      for (let index = 1; index <= 12; index += 1) {
        const phase = t * Math.PI + index * Math.PI / 6;
        model.get(`box_${index}`).translate([0, 0, 4 * Math.sin(phase)]);
        model.get(`cylinder_${index}`).translate([0, 0, 4 * Math.cos(phase)]);
      }
    },
  },
};
