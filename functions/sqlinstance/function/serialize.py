"""Turn composed-resource models into what the Crossplane SDK accepts."""


def to_dict(model) -> dict:
    """Serialize a composed-resource model for resource.update().

    by_alias, because generated models alias fields whose CRD names collide with Python keywords,
    and resource.update() given a model dumps without it. exclude_none, so the manifest carries
    exactly the fields that were set.
    """
    return model.model_dump(by_alias=True, exclude_none=True, warnings=False)
