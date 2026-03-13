from abc import ABC, abstractmethod


# TODO: we might want to support a logP_of_seq method
class Model(ABC):
	"""
	This model class provide a consistent interface between all desired models
	(ex., chat vs non-chat, gpt vs non-gpt)
	"""
	def __init__(self, verbosity=0) -> None:
		self.verbosity = verbosity

	@abstractmethod
	def generate_text(self, input_text: str | list[str], generation_config=None, max_new_tokens=None):
		pass

	# NOTE: We don't make this an abstract method because some models don't allow access to log probs and you can still
	#		do a lot of experiments without them.
	def cond_logP(self, inputs: str | list[str], targets: list[str] | list[list[str]]) -> float | list[float]:
		raise NotImplementedError()
