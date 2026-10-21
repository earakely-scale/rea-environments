// Create, update and delete two scratch objects of one write target through a capture script's `api` helper, reading
// each back (object and list) before the next write; see CAPTURE.md, "Recording writes".
// target: { collection, list?, item?(id), id(created), create(n), update?(n, created), updateMethod?, beforeDelete?(id),
//           remove? }   n is 1 or 2; `remove: false` keeps the objects. Returns the created ids.
export const recordWrites = async (api, target) => {
  const read = async (id) => {
    if (target.item) await api('GET', target.item(id));
    if (target.list) await api('GET', target.list);
  };
  if (target.list) await api('GET', target.list);
  const created = [];
  for (const n of [1, 2]) {
    const response = await api('POST', target.collection, target.create(n));
    const id = target.id(response);
    if (id === undefined || id === null) throw new Error(`create ${n} on ${target.collection} returned no id`);
    created.push({ id, response });
    await read(id);
  }
  if (target.update) for (const [index, { id, response }] of created.entries()) {
    await api(target.updateMethod ?? 'PATCH', target.item ? target.item(id) : `${target.collection}/${id}`, target.update(index + 1, response));
    await read(id);
  }
  if (target.remove !== false) for (const { id } of created) {
    for (const [method, path, body] of target.beforeDelete?.(id) ?? []) await api(method, path, body);
    await api('DELETE', target.item ? target.item(id) : `${target.collection}/${id}`);
    await read(id);
  }
  return created.map(({ id }) => id);
};
