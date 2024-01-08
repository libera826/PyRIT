# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from __future__ import annotations

import abc
import hashlib
import re
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Literal, Optional, Type, TypeVar

import yaml
from pydantic import BaseModel, Extra


@dataclass
class Score:
    score_type: Literal["int", "float", "str", "bool"]
    score_value: int | float | str
    score_description: str = ""
    score_explanation: str = ""


class PromptResponse(BaseModel, extra=Extra.forbid):
    # The text response for the prompt
    completion: str
    # The original prompt
    prompt: str = ""
    # An unique identifier for the response
    id: str = ""
    # The number of tokens used in the completion
    completion_tokens: int = 0
    # The number of tokens sent in the prompt
    prompt_tokens: int = 0
    # Total number of tokens used in the request
    total_tokens: int = 0
    # The model used
    model: str = ""
    # The type of operation (e.g., "text_completion")
    object: str = ""
    # When the object was created
    created_at: int = 0
    logprobs: Optional[bool] = False
    index: int = 0
    # Rationale why the model ended (e.g., "stop")
    finish_reason: str = ""
    # The time it took to complete the request from the moment the API request
    # was made, in nanoseconds.
    api_request_time_to_complete_ns: int = 0

    # Extra metadata that can be added to the response
    metadata: dict = {}

    def save_to_file(self, directory_path: Path) -> str:
        """Save the Prompt Response to disk and return the path of the new file.

        Args:
            directory_path: The path to save the file to
        Returns:
            The full path to the file that was saved
        """
        embedding_json = self.json()
        embedding_hash = hashlib.sha256(embedding_json.encode()).hexdigest()
        embedding_output_file_path = Path(directory_path, f"{embedding_hash}.json")
        embedding_output_file_path.write_text(embedding_json)
        return embedding_output_file_path.as_posix()

    def to_json(self) -> str:
        return self.json()

    @staticmethod
    def load_from_file(file_path: Path) -> PromptResponse:
        """Load the Prompt Response from disk

        Args:
            file_path: The path to load the file from
        Returns:
            The loaded embedding response
        """
        embedding_json_data = file_path.read_text(encoding="utf-8")
        return PromptResponse.parse_raw(embedding_json_data)


@dataclass
class Prompt:
    content: str


@dataclass
class ScoreAnswers:
    answers: list[str]
    name: str = ""
    version: str = ""
    description: str = ""
    author: str = ""
    group: str = ""

    @staticmethod
    def from_yaml(file: Path) -> ScoreAnswers:
        yaml_data = yaml.safe_load(file.read_text("utf-8"))
        return ScoreAnswers(**yaml_data)


@dataclass
class ExamAnswer:
    answer: str
    explanation: str
    confidence: str


@dataclass
class ExamAnswers:
    answer: list[ExamAnswer] = field(default_factory=list)


@dataclass
class ScoringResults:
    failed: int
    passed: int
    # unknown: int
    questions_count: int
    passed_with_partial_credit: float


@dataclass
class CompletionConfig:
    temperature: int
    max_tokens: int


T = TypeVar("T", bound="YamlLoadable")


class YamlLoadable(abc.ABC):
    @classmethod
    def from_yaml_file(cls: Type[T], file: Path) -> T:
        """
        Creates a new object from a file
        Args:
            file: The input file

        Returns:
            A new T object
        Raises:
            FileNotFoundError: if the input YAML file path does not exist
        """
        if not file.exists():
            raise FileNotFoundError(f"File '{file}' does not exist.")
        try:
            yaml_data = yaml.safe_load(file.read_text("utf-8"))
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML file '{file}': {exc}")
        data_object = cls(**yaml_data)
        return data_object


@dataclass
class PromptDataset(YamlLoadable):
    name: str
    description: str
    harm_category: str
    author: str
    group: str
    should_be_blocked: bool
    prompts: list[str] = field(default_factory=list)


@dataclass
class AttackStrategy(YamlLoadable):
    """TODO. This is a temporary name and needs more discussion. We've thought about naming this Personality
    or Objective as well."""

    name: str
    description: str
    content: str


@dataclass
class PromptTemplate(YamlLoadable):
    template: str
    name: str = ""
    description: str = ""
    should_be_blocked: bool = False
    harm_category: str = ""
    author: str = ""
    group: str = ""
    parameters: list[str] = field(default_factory=list)

    def apply_custom_metaprompt_parameters(self, **kwargs) -> str:
        """Builds a new prompts from the metapromt template.
        Args:
            **kwargs: the key value for the metaprompt template inputs

        Returns:
            A new prompt following the template
        """
        final_prompt = self.template
        for key, value in kwargs.items():
            if key not in self.parameters:
                raise ValueError(f'Invalid parameters passed. [expected="{self.parameters}", actual="{kwargs}"]')
            # Matches field names within brackets {{ }}
            #  {{   key    }}
            #  ^^^^^^^^^^^^^^
            regex = "{}{}{}".format("\{\{ *", key, " *\}\}")  # noqa: W605
            matches = re.findall(pattern=regex, string=final_prompt)
            if not matches:
                raise ValueError(
                    f"No parameters matched, they might be missing in the template. "
                    f'[expected="{self.parameters}", actual="{kwargs}"]'
                )
            final_prompt = re.sub(pattern=regex, string=final_prompt, repl=value)
        return final_prompt


@dataclass
class MsftAnswerChoice:
    key: str
    value: str


@dataclass
class MsftAnswer:
    key: str


@dataclass
class MsftQuestion:
    question_id: str
    stem: str
    answer: MsftAnswer
    answer_choices: list[MsftAnswerChoice]
    objective: str
    rationale: str
    urls: list[str]


@dataclass
class MsftQuestions:
    questions: list[MsftQuestion]

    @staticmethod
    def from_dict(data: dict) -> MsftQuestions:
        msft_questions: list[MsftQuestion] = []
        for question_data in data["questions"]:
            answer_choices = [MsftAnswerChoice(**c) for c in question_data["answer_choices"]]
            answer = MsftAnswer(**question_data["answer"])
            urls = question_data["urls"].splitlines()
            q_obj = MsftQuestion(
                question_id=question_data["question_id"],
                answer=answer,
                stem=question_data["stem"],
                answer_choices=answer_choices,
                objective=question_data["objective"],
                rationale=question_data["rationale"],
                urls=urls,
            )
            msft_questions.append(q_obj)
        return MsftQuestions(questions=msft_questions)

    @staticmethod
    def from_yaml(yaml_data: str) -> MsftQuestions:
        dict_data = yaml.safe_load(yaml_data)
        return MsftQuestions.from_dict(dict_data)


class ChatMessage(BaseModel, extra=Extra.forbid):
    role: str
    content: str


class EmbeddingUsageInformation(BaseModel, extra=Extra.forbid):
    prompt_tokens: int
    total_tokens: int


class EmbeddingData(BaseModel, extra=Extra.forbid):
    embedding: list[float]
    index: int
    object: str


class EmbeddingResponse(BaseModel, extra=Extra.forbid):
    model: str
    object: str
    usage: EmbeddingUsageInformation
    data: list[EmbeddingData]

    def save_to_file(self, directory_path: Path) -> str:
        """Save the embedding response to disk and return the path of the new file

        Args:
            directory_path: The path to save the file to
        Returns:
            The full path to the file that was saved
        """
        embedding_json = self.json()
        embedding_hash = sha256(embedding_json.encode()).hexdigest()
        embedding_output_file_path = Path(directory_path, f"{embedding_hash}.json")
        embedding_output_file_path.write_text(embedding_json)
        return embedding_output_file_path.as_posix()

    @staticmethod
    def load_from_file(file_path: Path) -> EmbeddingResponse:
        """Load the embedding response from disk

        Args:
            file_path: The path to load the file from
        Returns:
            The loaded embedding response
        """
        embedding_json_data = file_path.read_text(encoding="utf-8")
        return EmbeddingResponse.parse_raw(embedding_json_data)

    def to_json(self) -> str:
        return self.json()
